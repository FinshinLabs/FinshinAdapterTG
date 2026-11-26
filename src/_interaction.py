"""Telegram 交互端口

- 统一文字外发、存在性探测与提及片段
- 媒体外发按内容种类交出去，本端口只管分派
"""

import asyncio
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from finshin_sdk import InteractionPort
from finshin_sdk.domain import ContentKind
from finshin_sdk.dto import MessageRefDTO, OutboundPayloadDTO, PrincipalDTO

from ._errors import guard_send, is_vanished
from ._fields import build_ref, chat_id_of, reply_id_of
from ._media import MediaSender, PhotoIdCache

if TYPE_CHECKING:
    from aiogram import Bot

# 外发分段
_SEGMENT_SIZE = 4000  # 字符，平台上限 4096 留 96 给提及前缀与实体偏移
_FLOOD_THRESHOLD = 5  # 段，总段数超此值时段间休眠防频控
_SEGMENT_SLEEP_SECONDS = 1.0  # 秒

_PROBE_TEXT = "dummy"  # 探测占位文本，仅用于触发服务端错误串


def _split_chunks(text: str) -> list[str]:
    """按分段阈值切片"""
    return [text[i : i + _SEGMENT_SIZE] for i in range(0, len(text), _SEGMENT_SIZE)]


class TelegramInteractionPort(InteractionPort):
    """Telegram 交互端口"""

    def __init__(self, bot: "Bot") -> None:
        self._bot = bot
        self._media = MediaSender(bot, PhotoIdCache())

    async def send_message(
        self,
        principal: PrincipalDTO,
        content: OutboundPayloadDTO,
        *,
        mention: bool = False,
        reply_ref: MessageRefDTO | None = None,
    ) -> MessageRefDTO | None:
        """发送消息

        - 超长文字自动分段
        - 媒体附言写入附文
        """
        if content.kind == ContentKind.TEXT:
            return await self._send_text(
                principal, content.text, mention=mention, reply_ref=reply_ref
            )
        if content.kind == ContentKind.UNKNOWN:
            raise ValueError(f"不支持的外发内容种类: {content.kind}")
        return await self._media.send(principal, content, reply_ref=reply_ref)

    async def probe_existence(self, target: MessageRefDTO) -> bool:
        """探测消息是否仍存在

        - 靠改写文本报出的错误串区分已删除与无权编辑
        - 禁止用于探测 bot 自己发的消息，文本会被真改成占位串
        """
        try:
            # 被探测的是用户消息，bot 无权编辑他人消息，改不动也不会真改动
            await self._bot.edit_message_text(
                chat_id=chat_id_of(target.container),
                message_id=int(target.message_id),
                text=_PROBE_TEXT,
            )
        except TelegramAPIError as exc:
            return not is_vanished(exc)
        return True

    def mention_fragment(self, principal: PrincipalDTO) -> str:
        """生成提及文本片段

        - 名称取用户段，深链只靠用户标识
        """
        return f"[{principal.user}](tg://user?id={principal.user})"

    async def _send_text(
        self,
        principal: PrincipalDTO,
        text: str,
        *,
        mention: bool,
        reply_ref: MessageRefDTO | None,
    ) -> MessageRefDTO | None:
        """发送文字

        - 超长按分段阈值切片
        """
        body = f"{self.mention_fragment(principal)} {text}" if mention else text
        chunks = _split_chunks(body)
        sent: Message | None = None
        for index, chunk in enumerate(chunks):
            sent = await guard_send(
                self._bot.send_message(
                    chat_id=chat_id_of(principal.container),
                    text=chunk,
                    reply_to_message_id=reply_id_of(reply_ref),
                ),
                reply_ref,
            )
            if len(chunks) > _FLOOD_THRESHOLD and index < len(chunks) - 1:
                await asyncio.sleep(_SEGMENT_SLEEP_SECONDS)

        return build_ref(sent, principal.container) if sent is not None else None
