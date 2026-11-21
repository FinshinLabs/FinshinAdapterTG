"""Telegram 适配器入口

- 交出配置段、装配、检查计划、预热、平台显示名与凭证声明
"""

from finshin_sdk import AdapterParts, BaseAdapter

from ._config import SECTIONS
from ._credential import CREDENTIAL
from ._plan import build_connection_plan
from ._probe import preload_engine


def _assemble(token: str, proxy: str | None) -> BaseAdapter:
    """造出 Telegram 的运行时"""
    # 起主窗不等引擎库，适配器到函数体内才入场
    from ._adapter import TelegramAdapter

    return TelegramAdapter(token=token, proxy=proxy)


def parts() -> AdapterParts:
    """交出本适配器入口模块的六件"""
    return AdapterParts(
        title="Telegram",
        sections=SECTIONS,
        assemble=_assemble,
        plan_for=build_connection_plan,
        engine_preload=preload_engine,
        credential=CREDENTIAL,
    )
