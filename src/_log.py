"""适配层日志口径

- 日志器名一处定死，各件共用
"""

from finshin_sdk import LogLevel, log

_SOURCE = "Adapter"  # 本适配器的日志器名，归一、相册与外发共用


def note(msg: str) -> None:
    """写一行调试档"""
    log(_SOURCE, LogLevel.DEBUG, msg)


def fail(msg: str, e: BaseException) -> None:
    """记一处兜住的异常"""
    log(_SOURCE, LogLevel.ERROR, msg, exc=e)
