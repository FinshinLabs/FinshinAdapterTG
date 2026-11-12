"""Telegram 适配器入口

- 交出装配、探测与预热三件
"""

from finshin_sdk import AdapterParts, BaseAdapter

from ._probe import attempt_channel, preload_engine


def _assemble(token: str, proxy: str | None) -> BaseAdapter:
    """造出 Telegram 的运行时"""
    # 起主窗不等引擎库，适配器到函数体内才入场
    from ._adapter import TelegramAdapter

    return TelegramAdapter(token=token, proxy=proxy)


def parts() -> AdapterParts:
    """交出本适配器入口模块的三件"""
    return AdapterParts(
        assemble=_assemble,
        channel_probe=attempt_channel,
        engine_preload=preload_engine,
    )
