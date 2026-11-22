"""宁夏兰星天然气 API 客户端（免登录查询链路）.

用户名 + 用户编码即可查到名下所有燃气账户及余额；可选 OpenID 解锁
远传表实时数据（剩余方数 / 累计用气 / 上次结算时间）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CUSTCODE,
    CONF_CUSTNAME,
    CONF_DETAIL_ENDPOINT,
    CONF_GATEWAY_URL,
    CONF_HEADERS,
    CONF_INFO_ENDPOINT,
    CONF_METER_ENDPOINT,
    CONF_METHOD,
    CONF_OPENID,
    CONF_PHONE,
    CONF_SEARCH_ENDPOINT,
    DEFAULT_DETAIL_ENDPOINT,
    DEFAULT_GATEWAY_URL,
    DEFAULT_HEADERS,
    GATEWAY_REFERER,
    GATEWAY_UA,
    DEFAULT_INFO_ENDPOINT,
    DEFAULT_METER_ENDPOINT,
    DEFAULT_METHOD,
    DEFAULT_SEARCH_ENDPOINT,
    DEFAULT_TIMEZONE,
)

_LOGGER = logging.getLogger(__name__)


class LanxingGasError(Exception):
    """Base error."""


class LanxingGasAuthError(LanxingGasError):
    """Credentials rejected."""


class LanxingGasResponseError(LanxingGasError):
    """Response malformed."""


@dataclass(slots=True)
class AccountReading:
    """One bound gas account and its known values."""

    cust_id: str
    cust_code: str
    cust_name: str
    address: str
    balance: float | None = None
    meter_code: str | None = None
    phone: str | None = None
    meter_type: str | None = None
    remote_buy_num: float | None = None
    last_buy_num: float | None = None
    last_buy_date: str | None = None
    last_gas: float | None = None
    total_gas: float | None = None
    last_settled: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _to_float(value: Any) -> float | None:
    """Best-effort numeric conversion, None when unavailable."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    for ch in ("元", "方", "￥", " "):
        text = text.replace(ch, "")
    try:
        return float(text)
    except ValueError:
        return None


def _to_datetime(value: Any) -> datetime | None:
    """Parse an API timestamp into an aware datetime."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
    return parsed


class LanxingGasApiClient:
    """Client that mirrors the mini program's no-login query flow."""

    def __init__(self, hass: HomeAssistant, config: Mapping[str, Any]) -> None:
        self.hass = hass
        self.cust_code = str(config.get(CONF_CUSTCODE, "") or "").strip()
        self.cust_name = str(config.get(CONF_CUSTNAME, "") or "").strip()
        self.phone = str(config.get(CONF_PHONE, "") or "").strip()
        self.openid = str(config.get(CONF_OPENID, "") or "").strip()
        self.gateway_url = str(
            config.get(CONF_GATEWAY_URL, DEFAULT_GATEWAY_URL) or DEFAULT_GATEWAY_URL
        )
        self.search_endpoint = str(
            config.get(CONF_SEARCH_ENDPOINT, DEFAULT_SEARCH_ENDPOINT)
            or DEFAULT_SEARCH_ENDPOINT
        )
        self.info_endpoint = str(
            config.get(CONF_INFO_ENDPOINT, DEFAULT_INFO_ENDPOINT)
            or DEFAULT_INFO_ENDPOINT
        )
        self.meter_endpoint = str(
            config.get(CONF_METER_ENDPOINT, DEFAULT_METER_ENDPOINT)
            or DEFAULT_METER_ENDPOINT
        )
        self.detail_endpoint = str(
            config.get(CONF_DETAIL_ENDPOINT, DEFAULT_DETAIL_ENDPOINT)
            or DEFAULT_DETAIL_ENDPOINT
        )
        self._headers_text = str(config.get(CONF_HEADERS, DEFAULT_HEADERS) or "")
        self.method = str(config.get(CONF_METHOD, DEFAULT_METHOD) or DEFAULT_METHOD).upper()

    def _headers(self) -> dict[str, str]:
        try:
            parsed = json.loads(self._headers_text)
        except json.JSONDecodeError:
            parsed = {}
        headers = {"Content-Type": "application/json"}
        if isinstance(parsed, dict):
            headers.update({str(k): str(v) for k, v in parsed.items()})
        return headers

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=ClientTimeout(total=20),
            ) as response:
                if response.status != 200:
                    raise LanxingGasResponseError(f"接口返回 HTTP {response.status}")
                text = await response.text()
        except ClientError as err:
            raise LanxingGasError(f"请求失败: {err}") from err
        try:
            body = json.loads(text)
        except json.JSONDecodeError as err:
            raise LanxingGasResponseError("接口响应不是合法 JSON") from err
        if not isinstance(body, dict):
            raise LanxingGasResponseError("接口响应格式异常")
        return body

    def _ok(self, body: Mapping[str, Any]) -> bool:
        return str(body.get("RespCode", "")) == "10000"

    async def async_gateway_realtime(self) -> dict[str, Any]:
        """Fetch real-time volume from the service-account Balance page.

        The WeChat service-account H5 page renders live meter values directly
        in its HTML. With the fixed P token plus a WeChat UA/Referer it is
        publicly readable and does not need an OpenID or login session.
        Returns keys: last_gas, total_gas, last_settled, openid, by_meter.
        """
        result: dict[str, Any] = {"by_meter": {}}
        if not self.gateway_url:
            return result
        # If the URL contains {openid}, fill it from the configured OpenID.
        # Without an OpenID the page cannot return data, so skip early.
        url = self.gateway_url
        if "{openid}" in url:
            if not self.openid:
                return result
            url = url.replace("{openid}", self.openid)
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                url,
                headers={"User-Agent": GATEWAY_UA, "Referer": GATEWAY_REFERER},
                timeout=ClientTimeout(total=20),
            ) as response:
                html = await response.text()
        except ClientError as err:
            _LOGGER.debug("网关余额页请求失败: %s", err)
            return result

        # OpenID embedded in the payment link
        m_openid = re.search(r"OpenID=([A-Za-z0-9_-]{20,40})", html)
        if m_openid:
            result["openid"] = m_openid.group(1)

        # Each meter block: <div class="meter-item">... meter-label ... values
        for block in re.findall(r'<div class="meter-item">(.*?)</div></div>', html, re.S):
            m_meter = re.search(r"(\d{10})\s*\(类型:(\d+)\)", block)
            m_remain = re.search(r'meter-value[^>]*>([\d.]+)\s*方', block)
            m_total = re.search(r"累计用气[:：]\s*([\d.]+)\s*方", block)
            m_settle = re.search(r"上次结算[:：]\s*([\d-]+\s+[\d:]+)", block)
            if not m_meter or not m_remain:
                continue
            meter_no = m_meter.group(1)
            result["by_meter"][meter_no] = {
                "last_gas": _to_float(m_remain.group(1)),
                "total_gas": _to_float(m_total.group(1)) if m_total else None,
                "last_settled": _to_datetime(m_settle.group(1)) if m_settle else None,
            }
        return result

    async def async_search_accounts(self) -> list[dict[str, Any]]:
        """Find all accounts for the given custcode + custname."""
        if not self.cust_code:
            raise LanxingGasError("用户编码不能为空")
        if not self.cust_name:
            raise LanxingGasError("用户名称不能为空")
        body = await self._post(
            self.search_endpoint,
            {"openid": "", "custcode": self.cust_code, "custname": self.cust_name},
        )
        if not self._ok(body):
            raise LanxingGasResponseError(
                f"账户查询失败: {body.get('RespMsg', body.get('Result'))}"
            )
        result = body.get("Result")
        return result if isinstance(result, list) else []

    async def async_fetch_account(self, account: Mapping[str, Any]) -> AccountReading:
        """Fetch details for one account via the no-login GetCustInfo endpoint."""
        cust_id = str(account.get("custid", "") or "")
        if not cust_id:
            raise LanxingGasResponseError("账户缺少 custid")
        body = await self._post(self.info_endpoint, {"CustID": cust_id})
        if not self._ok(body):
            raise LanxingGasResponseError(
                f"账户详情查询失败: {body.get('RespMsg', body.get('Result'))}"
            )
        result = body.get("Result") or {}
        infos = result.get("CustInfos") or []
        info = infos[0] if infos else {}
        meters = result.get("MeterInfos") or []
        meter = meters[0] if meters else {}

        # GetCustInfo often returns MeterInfos=null; fetch meter data separately.
        if not meter and self.meter_endpoint:
            try:
                mbody = await self._post(self.meter_endpoint, {"CustID": cust_id})
                if self._ok(mbody):
                    mlist = (mbody.get("Result") or {}).get("MeterInfos") or []
                    meter = mlist[0] if mlist else {}
            except LanxingGasError as err:
                _LOGGER.debug("表信息查询跳过: %s", err)

        reading = AccountReading(
            cust_id=cust_id,
            cust_code=str(info.get("CustCode") or account.get("custcode", "")),
            cust_name=str(info.get("CustName") or account.get("custname", "")),
            address=str(info.get("CustAdd") or account.get("custadd", "")),
            balance=_to_float(info.get("NowBalance")),
            meter_code=str(meter.get("MeterCode") or "") or None,
            phone=str(info.get("CustTel_Mobile") or "") or None,
            meter_type=str(meter.get("MeterType_Name") or "") or None,
            remote_buy_num=_to_float(meter.get("Remote_BuyNum")),
            last_buy_num=_to_float(meter.get("IC_LastBuyNum")),
            last_buy_date=str(meter.get("IC_LastBuyDate") or "") or None,
            raw={"account": dict(body.get("Result") or {}), "bound": dict(account)},
        )

        if self.openid:
            try:
                detail = await self._post(
                    self.detail_endpoint,
                    {
                        "MeterID": str(account.get("meterid", "") or ""),
                        "CustID": cust_id,
                        "OpenID": self.openid,
                    },
                )
                if self._ok(detail) and isinstance(detail.get("Result"), dict):
                    d = detail["Result"]
                    reading.last_gas = _to_float(d.get("LastGas"))
                    reading.total_gas = _to_float(d.get("UsedGas"))
                    reading.last_settled = _to_datetime(d.get("LastSettleTime"))
                    reading.raw["detail"] = d
            except LanxingGasError as err:
                _LOGGER.debug("实时余量查询跳过: %s", err)
        return reading

    async def async_fetch_my_accounts(self) -> list[AccountReading]:
        """Fetch all accounts and keep only those matching the reserved phone.

        The search endpoint ignores the phone parameter, so namesakes can be
        returned. Filtering on the phone returned by GetCustInfo is what
        actually isolates the user's own accounts.
        """
        accounts = await self.async_search_accounts()
        readings: list[AccountReading] = []
        for account in accounts:
            reading = await self.async_fetch_account(account)
            if self.phone and reading.phone != self.phone:
                _LOGGER.debug(
                    "跳过非本人账户 %s（电话 %s ≠ %s）",
                    reading.cust_code,
                    reading.phone,
                    self.phone,
                )
                continue
            readings.append(reading)
        return readings

    async def async_validate(self) -> list[AccountReading]:
        """Validate by fetching accounts filtered by phone."""
        return await self.async_fetch_my_accounts()
