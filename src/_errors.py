"""平台异常翻译

- 交出本平台连接性异常族
- 把 Telegram 错误串归一为领域异常
- 发送处按引用目标是否失效决定要不要翻译
"""

from collections.abc import Awaitable

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from finshin_sdk.dto import MessageRefDTO
from finshin_sdk.exceptions import ConnectivityError, MessageVanishedError


class DirectTimeoutError(ConnectivityError):
    """无代理直连超时"""


class TokenError(ConnectivityError):
    """Token 异常"""


class TokenFormatError(TokenError):
    """Token 形状不对"""


class ProxyError(ConnectivityError):
    """代理异常基类"""

    def __init__(self, proxy: str) -> None:
        self.proxy = proxy
        super().__init__()


class ProxySchemeError(ProxyError):
    """代理协议头错误"""

    def __init__(self, scheme: str, proxy: str = "") -> None:
        self.scheme = scheme
        super().__init__(proxy)


class ProxySchemeMissingError(ProxySchemeError):
    """代理地址没写协议头"""

    def __init__(self, proxy: str) -> None:
        super().__init__(scheme="", proxy=proxy)


class ProxyAddressError(ProxyError):
    """代理地址解析错误"""


class ProxyConnectionRefusedError(ProxyError):
    """代理连接被拒绝"""


class ProxyTimeoutError(ProxyError):
    """代理连接超时"""


# 服务端表示消息已不存在的错误串
_VANISHED_MARKS = (
    "message to edit not found",
    "message to be replied not found",
    "message_invalid_id",
)


def is_vanished(exc: TelegramAPIError) -> bool:
    """消息已删除错误判定"""
    text = str(exc).lower()
    return any(mark in text for mark in _VANISHED_MARKS)


async def guard_send(
    awaitable: Awaitable[Message], reply_ref: MessageRefDTO | None
) -> Message:
    """执行一次发送

    - 无引用目标时原样上抛
    """
    try:
        return await awaitable
    except TelegramAPIError as exc:
        if reply_ref is not None:
            raise translate(exc, reply_ref) from None
        raise


def translate(exc: TelegramAPIError, ref: MessageRefDTO) -> Exception:
    """翻译平台异常

    - 命中删除态标记返回消息不存在
    - 其余原样返回交调用方上抛
    """
    if is_vanished(exc):
        return MessageVanishedError(ref)
    return exc
