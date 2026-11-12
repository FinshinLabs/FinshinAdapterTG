"""平台异常翻译

- 把 Telegram 错误串归一为领域异常
- 发送处按引用目标是否失效决定要不要翻译
"""

from collections.abc import Awaitable

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from finshin_sdk.dto import MsgReferenceDTO
from finshin_sdk.exceptions import MessageVanishedError

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
    awaitable: Awaitable[Message], reply_ref: MsgReferenceDTO | None
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


def translate(exc: TelegramAPIError, ref: MsgReferenceDTO) -> Exception:
    """翻译平台异常

    - 命中删除态标记返回消息不存在
    - 其余原样返回交调用方上抛
    """
    if is_vanished(exc):
        return MessageVanishedError(ref)
    return exc
