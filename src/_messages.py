"""Telegram 检查文案

- 进度表行名、通道称谓与代理类错误句
- 只改文案不改调度，调度按接口包给的公开数据跑
"""


class ConnectionMessage:
    """连通检查的界面与日志文案"""

    ROW_CFG = "配置代理通道"
    ROW_SYS = "系统代理通道"
    ROW_DIRECT = "直连通道"

    VIA_DIRECT = "直连"
    VIA_PROXY = "代理 {proxy}"
    VIA_CFG = "配置代理 {proxy}"
    VIA_SYSTEM = "系统代理 {proxy}"

    CFG_EMPTY = "未配置（请填写代理地址）"
    SYS_UNAVAILABLE = "无可用系统代理（未开启或地址不可解析）"
    SYS_DEDUP = "跳过（与配置代理同端口）"
    MODE_CFG_ABSENT = "代理项为空，本模式只测该项，请先填写代理地址"
    MODE_SYS_ABSENT = "系统代理未开启或地址不可解析，请先开启系统代理"

    DIAG_ADVICE_NONE = "未找到可用通道：启动代理软件后重试，或开启 TUN"
    ALL_FAIL = "配置代理 / 系统代理 / 直连均无法连通"
    PROXY_GUIDE = "请到代理软件里确认监听端口与地址后重试"
    STALE = "配置代理 {raw!r} 不可用，本次改用{via}，请自行修正"
    PASS = "连通校验通过：生效通道 {via}"

    TOKEN_INVALID = "Token 无效"
    TOKEN_MALFORMED = "Token 格式错误（应为 数字:密钥）"
    SERVER_UNREACHABLE = "无法连接到服务器"
    DIRECT_TIMEOUT = "直连超时，请开启系统代理或在代理项填写地址"
    PROXY_INVALID = "代理地址有问题：{proxy}"
    SCHEME_UNSUPPORTED = "代理协议不支持: {scheme}"
    SCHEME_MISSING = "代理地址缺少 :// 协议头，收到的是 {proxy}"
    ADDRESS_UNPARSABLE = "代理地址格式无法解析: {proxy}"
    PROXY_REFUSED = "无法连接到代理服务器 {proxy}，请检查代理工具是否开启"
    PROXY_TIMEOUT = "连接代理 {proxy} 超时，请检查网络环境"

    TIMEOUT = "验证超时，请稍后重试"
    CRASH = "检查异常，详情见日志"
    COST = "通道 {via} 探测耗时 {cost:.1f}s"
