"""宁夏兰星天然气集成的配置流程：用户编码 + 用户名称即可。"""

from __future__ import annotations

import logging
from typing import Any, Mapping

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import TextSelector

from .api import LanxingGasApiClient, LanxingGasError, LanxingGasResponseError
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
    CONF_SCAN_INTERVAL,
    CONF_SEARCH_ENDPOINT,
    captured_defaults,
    DEFAULT_METHOD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

METHODS = ["POST", "GET"]


def _user_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    """Main form: custcode + custname required; openid optional."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_CUSTCODE, default=defaults.get(CONF_CUSTCODE, "")): TextSelector(),
            vol.Required(CONF_CUSTNAME, default=defaults.get(CONF_CUSTNAME, "")): TextSelector(),
            vol.Required(CONF_PHONE, default=defaults.get(CONF_PHONE, "")): TextSelector(),
            vol.Optional(CONF_OPENID, default=defaults.get(CONF_OPENID, "")): TextSelector(),
        }
    )


def _advanced_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Hidden capture parameters, editable only via reconfigure."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SEARCH_ENDPOINT, default=defaults.get(CONF_SEARCH_ENDPOINT, "")
            ): cv.string,
            vol.Optional(
                CONF_INFO_ENDPOINT, default=defaults.get(CONF_INFO_ENDPOINT, "")
            ): cv.string,
            vol.Optional(
                CONF_METER_ENDPOINT, default=defaults.get(CONF_METER_ENDPOINT, "")
            ): cv.string,
            vol.Optional(
                CONF_DETAIL_ENDPOINT, default=defaults.get(CONF_DETAIL_ENDPOINT, "")
            ): cv.string,
            vol.Optional(
                CONF_GATEWAY_URL, default=defaults.get(CONF_GATEWAY_URL, "")
            ): cv.string,
            vol.Optional(CONF_HEADERS, default=defaults.get(CONF_HEADERS, "")): cv.string,
            vol.Optional(
                CONF_METHOD, default=defaults.get(CONF_METHOD, DEFAULT_METHOD)
            ): vol.In(METHODS),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        }
    )


def _full_data(user_input: Mapping[str, Any]) -> dict[str, Any]:
    data = captured_defaults()
    data.update(user_input)
    return data


class LanxingGasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Lanxing gas config flow."""

    VERSION = 1

    async def _async_validate(self, data: Mapping[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not str(data.get(CONF_CUSTCODE, "")).strip():
            errors[CONF_CUSTCODE] = "required"
        if not str(data.get(CONF_CUSTNAME, "")).strip():
            errors[CONF_CUSTNAME] = "required"
        if not str(data.get(CONF_PHONE, "")).strip():
            errors[CONF_PHONE] = "required"
        if errors:
            return errors
        try:
            client = LanxingGasApiClient(self.hass, data)
            accounts = await client.async_validate()
            if not accounts:
                errors["base"] = "no_accounts"
        except LanxingGasResponseError as err:
            _LOGGER.debug("响应错误: %s", err)
            errors["base"] = "invalid_response"
        except LanxingGasError as err:
            _LOGGER.debug("连接错误: %s", err)
            errors["base"] = "cannot_connect"
        return errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for custcode + custname (and optional openid)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _full_data(user_input)
            errors = await self._async_validate(data)
            if not errors:
                meter = f"{user_input.get(CONF_CUSTCODE, '')}_{user_input.get(CONF_CUSTNAME, '')}"
                await self.async_set_unique_id(meter)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"兰星燃气 {user_input.get(CONF_CUSTNAME, '')}",
                    data=data,
                )
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Advanced: update captured endpoints."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(entry.data)
            data.update(user_input)
            errors = await self._async_validate(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_advanced_schema(user_input or entry.data),
            errors=errors,
        )
