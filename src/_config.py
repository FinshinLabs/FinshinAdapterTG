"""Telegram 配置段

- 交出代理模式与代理地址两项
- 代理地址的显隐由字段级条件声明，窗口不点名字段
"""

from finshin_sdk.domain import FieldCondition, FieldSpec, SectionSpec

# 段名与段表，入口件只交 SECTIONS
_SECTION = "proxy"
_PROXY_SECTION = SectionSpec(
    section=_SECTION,
    title="连接与代理",
    fields=(
        FieldSpec(
            section=_SECTION,
            key="proxy_mode",
            value_type=str,
            default="auto",
            label="代理模式",
            desc="自动档三路逐项尝试，单路档只走选定一路",
            options=("auto", "cfg", "sys", "direct"),
            option_labels=(
                "自动（配置→系统→直连）",
                "仅配置代理",
                "仅系统代理",
                "仅直连（代理软件开 TUN 时选这个）",
            ),
        ),
        FieldSpec(
            section=_SECTION,
            key="proxy",
            value_type=str,
            default="",
            label="代理",
            desc="从代理软件获取填写",
            visible_when=(FieldCondition("proxy_mode", ("auto", "cfg")),),
        ),
    ),
)

SECTIONS = (_PROXY_SECTION,)
