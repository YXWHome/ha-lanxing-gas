"""宁夏兰星天然气集成常量.

逆向自微信小程序「宁夏兰星天然气」(appid wx6db805328898c8ad)。
实测确认的免登录查询链路：

  1) SearchCustWithBind  POST :8826/api/MiniApps_CustInfo/SearchCustWithBind
     data: {openid:"", custcode:<用户编码>, custname:<用户名称>}
     -> 返回该户主名下所有绑定账户 (custid/custcode/custadd/state)
     -> 无需密码、无需微信 code、无需 OpenID（openid 传空即可）

  2) GetCustInfo  POST :8827/api/BaseInfo/GetCustInfo
     data: {CustID:<数字>}
     -> 客户姓名/编号/地址/电话/余额(NowBalance) 等 143 个字段
     -> 完全免登录

实时远传表数据（剩余方数/累计用气/结算时间）走
GetBindCustInfoDetails，需要微信为该账户生成的真实 OpenID，本地不可得；
作为可选增强：用户填入 OpenID 即可解锁。
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import Platform

DOMAIN = "lanxing_gas"
PLATFORMS: list[Platform] = [Platform.SENSOR]

# 配置界面字段
CONF_CUSTCODE = "custcode"       # 用户编码（12位）
CONF_CUSTNAME = "custname"       # 用户名称
CONF_PHONE = "phone"             # 预留手机号（可选，界面保留）
CONF_OPENID = "openid"           # 可选：解锁实时余量

# 高级参数（隐藏）
CONF_SEARCH_ENDPOINT = "search_endpoint"
CONF_INFO_ENDPOINT = "info_endpoint"
CONF_METER_ENDPOINT = "meter_endpoint"
CONF_DETAIL_ENDPOINT = "detail_endpoint"
CONF_GATEWAY_URL = "gateway_url"  # 服务号余额查询页（含实时余量）
CONF_HEADERS = "headers"
CONF_METHOD = "method"
CONF_SCAN_INTERVAL = "scan_interval"

# 服务与固定请求头
HOST_API = "https://www.lxtrq.com:8826"
HOST_CORE = "https://www.lxtrq.com:8827"
COMMON_HEADERS = (
    '{"AccessToken": "29F87FC7F3307BF0BDF29AAB9460ED4C", '
    '"Authorization": "emhvdW5hOjIwMTkxMjI0MTQwMjMy"}'
)

DEFAULT_SEARCH_ENDPOINT = HOST_API + "/api/MiniApps_CustInfo/SearchCustWithBind"
DEFAULT_INFO_ENDPOINT = HOST_CORE + "/api/BaseInfo/GetCustInfo"
DEFAULT_METER_ENDPOINT = HOST_CORE + "/api/BaseInfo/GetMeterInfo"
DEFAULT_DETAIL_ENDPOINT = HOST_API + "/api/MiniApps_UserInfo/GetBindCustInfoDetails"
# 服务号 H5 余额页：固定 P 令牌，带微信 UA + Referer 即可返回实时余量
# （页面 HTML 内含 剩余气量/累计用气/上次结算），作为 OpenID 接口的替代数据源
DEFAULT_GATEWAY_URL = (
    "http://www.lxtrq.com/WeiXin/Process/Balance.aspx"
    "?P=CFA098A813709A7029C65BBB42C8A2DC3E39FB598F6DC67BD221DA5EB51AAC696C49F8CAF852CD1F91DEFD7C5E8A3B6CF639BD3B6E24061C"
)
GATEWAY_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 MicroMessenger/8.0"
GATEWAY_REFERER = "http://www.lxtrq.com/WeiXin/Process/Index.aspx"
DEFAULT_HEADERS = COMMON_HEADERS
DEFAULT_METHOD = "POST"
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def captured_defaults() -> dict[str, Any]:
    """Return default API parameters for a config entry."""
    return {
        CONF_SEARCH_ENDPOINT: DEFAULT_SEARCH_ENDPOINT,
        CONF_INFO_ENDPOINT: DEFAULT_INFO_ENDPOINT,
        CONF_METER_ENDPOINT: DEFAULT_METER_ENDPOINT,
        CONF_DETAIL_ENDPOINT: DEFAULT_DETAIL_ENDPOINT,
        CONF_GATEWAY_URL: DEFAULT_GATEWAY_URL,
        CONF_HEADERS: DEFAULT_HEADERS,
        CONF_METHOD: DEFAULT_METHOD,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }
