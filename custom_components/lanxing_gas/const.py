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
# 服务号 H5 余额页：带微信 UA + Referer，用 {openid} 即可返回实时余量
# （页面 HTML 内含 剩余气量/累计用气/上次结算）。OpenID 长期有效，
# 不像 OAuth 的 P 令牌会过期；{openid} 由配置中的 OpenID 字段替换。
DEFAULT_GATEWAY_URL = (
    "http://www.lxtrq.com/WeiXin/Process/Balance.aspx?OpenID={openid}"
)
GATEWAY_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 MicroMessenger/8.0"
GATEWAY_REFERER = "http://www.lxtrq.com/WeiXin/Process/Index.aspx"
DEFAULT_HEADERS = COMMON_HEADERS
DEFAULT_METHOD = "POST"
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 银川市居民生活用气阶梯气价（来源：宁夏兰星天然气官方公众号公示，
# 依据银发改发〔2023〕150号，2023-07-20 起执行；单价 元/方，按自然年用量）。
# 若政策调整，更新这三档边界/单价即可。
TIER_PRICES = (
    (336.0, 2.09),   # 第一档 0-336(含)
    (480.0, 2.51),   # 第二档 336-480(含)
    (float("inf"), 3.14),  # 第三档 >480
)
# 壁挂炉用户档位（居民采暖），当前集成默认用居民生活档；如需可切换。
TIER_PRICES_HEATING = (
    (2245.0, 2.09),
    (3075.0, 2.51),
    (float("inf"), 3.14),
)


def marginal_price(annual_usage: float, heating: bool = False) -> float:
    """Return the marginal (current tier) unit price for a given annual usage."""
    tiers = TIER_PRICES_HEATING if heating else TIER_PRICES
    for limit, price in tiers:
        if annual_usage <= limit:
            return price
    return tiers[-1][1]


def tier_label(annual_usage: float, heating: bool = False) -> str:
    """Return a human-readable tier label for the given annual usage."""
    tiers = TIER_PRICES_HEATING if heating else TIER_PRICES
    names = ("第一档", "第二档", "第三档")
    for i, (limit, price) in enumerate(tiers):
        if annual_usage <= limit:
            return f"{names[i]}（{price} 元/方）"
    return f"{names[-1]}（{tiers[-1][1]} 元/方）"


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
