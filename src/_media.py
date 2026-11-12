"""媒体外发

- 按内容种类选原生形态，形态被拒即改按文件发
- 同一份本地照片重复外发改按已上传的标识发
"""

from pathlib import Path
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, Message

from finshin_sdk.domain import ContentKind
from finshin_sdk.dto import MsgReferenceDTO, OutboundPayloadDTO, PrincipalDTO

from ._errors import guard_send, is_vanished, translate
from ._fields import build_ref, chat_id_of, reply_id_of
from ._log import note

if TYPE_CHECKING:
    from aiogram import Bot

# 记下条数上限，超出即淘汰最先记进来的那条
_MAX_ENTRIES = 64

# 一份本地文件的身份：路径、改动时刻与字节数
_FileKey = tuple[str, int, int]


def _photo_id_of(sent: Message) -> str | None:
    """从发送回执取照片的远端标识

    - 回执按分辨率从小到大列出各档，末档即整图
    - 回执没带照片即没有标识可记
    """
    sizes = sent.photo
    return sizes[-1].file_id if sizes else None


class PhotoIdCache:
    """按本地文件身份记下远端标识

    - 进程级一份，重启即空表
    """

    def __init__(self) -> None:
        self._ids: dict[_FileKey, str] = {}

    def key_of(self, local_path: str) -> _FileKey | None:
        """按文件现状算出身份键

        - 重画即改时刻与字节数，旧标识自然失效
        - 文件取不到即没有键，这次外发不参与缓存
        """
        try:
            info = Path(local_path).stat()
        except OSError:
            return None
        return (local_path, info.st_mtime_ns, info.st_size)

    def take(self, key: _FileKey) -> str | None:
        """取文件已记下的标识"""
        return self._ids.get(key)

    def remember(self, key: _FileKey, file_id: str) -> None:
        """记下这份文件的标识"""
        if len(self._ids) >= _MAX_ENTRIES and key not in self._ids:
            self._ids.pop(next(iter(self._ids)))
        self._ids[key] = file_id

    def drop(self, key: _FileKey) -> None:
        """扔掉一条平台拒认的标识"""
        self._ids.pop(key, None)


class MediaSender:
    """媒体外发

    - 一份已上传标识表配一只端口，跨平台实例之间不共用
    """

    def __init__(self, bot: "Bot", photo_ids: PhotoIdCache) -> None:
        self._bot = bot
        self._photo_ids = photo_ids

    async def send(
        self,
        principal: PrincipalDTO,
        content: OutboundPayloadDTO,
        *,
        reply_ref: MsgReferenceDTO | None,
    ) -> MsgReferenceDTO | None:
        """发送媒体

        - 同一份照片重复外发时按已记下的标识发，文件体只传一次
        - 形态被拒即改按文件发
        - 文件名缺省取路径末段
        - 引用原消息已删属目标失效，不换形态重发
        """
        file = FSInputFile(content.local_path, filename=content.file_name or None)
        caption = content.text or None
        chat_id = chat_id_of(principal.container)
        reply_id = reply_id_of(reply_ref)
        photo_key = (
            self._photo_ids.key_of(content.local_path)
            if content.kind == ContentKind.PHOTO
            else None
        )
        try:
            sent = await guard_send(
                self._native(content.kind, file, caption, chat_id, reply_id, photo_key),
                reply_ref,
            )
        except TelegramAPIError as exc:
            if reply_ref is not None and is_vanished(exc):
                raise translate(exc, reply_ref) from None
            if content.kind == ContentKind.DOCUMENT:
                raise
            sent = await guard_send(
                self._bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    caption=caption,
                    reply_to_message_id=reply_id,
                ),
                reply_ref,
            )

        return build_ref(sent, principal.container)

    async def _native(
        self,
        kind: ContentKind,
        file: FSInputFile,
        caption: str | None,
        chat_id: int,
        reply_id: int | None,
        photo_key: _FileKey | None,
    ) -> Message:
        """按内容种类选原生形态发送

        - 音频一律走语音条，能不能显成播放器由平台判定
        - 词表内没有专属形态的种类按文件发
        """
        match kind:
            case ContentKind.PHOTO:
                return await self._photo(file, caption, chat_id, reply_id, photo_key)
            case ContentKind.VIDEO:
                return await self._bot.send_video(
                    chat_id=chat_id,
                    video=file,
                    caption=caption,
                    reply_to_message_id=reply_id,
                )
            case ContentKind.ANIMATION:
                return await self._bot.send_animation(
                    chat_id=chat_id,
                    animation=file,
                    caption=caption,
                    reply_to_message_id=reply_id,
                )
            case ContentKind.AUDIO:
                return await self._bot.send_voice(
                    chat_id=chat_id,
                    voice=file,
                    caption=caption,
                    reply_to_message_id=reply_id,
                )
            case _:
                return await self._bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    caption=caption,
                    reply_to_message_id=reply_id,
                )

    async def _photo(
        self,
        file: FSInputFile,
        caption: str | None,
        chat_id: int,
        reply_id: int | None,
        photo_key: _FileKey | None,
    ) -> Message:
        """发送照片

        - 没记过标识即上传本体，从回执记下标识
        - 平台不认这个标识即扔掉这条，改回本体重传一次
        """
        stored = self._photo_ids.take(photo_key) if photo_key is not None else None
        body_sent = stored is None
        try:
            sent = await self._post(
                file if stored is None else stored, caption, chat_id, reply_id
            )
        except TelegramAPIError:
            if stored is None or photo_key is None:
                raise
            self._photo_ids.drop(photo_key)
            sent = await self._post(file, caption, chat_id, reply_id)
            body_sent = True
        if photo_key is None:
            return sent
        file_id = _photo_id_of(sent)
        if file_id is not None:
            self._photo_ids.remember(photo_key, file_id)
            note(f"照片{'上传本体' if body_sent else '按标识重发'}：{file_id}")
        return sent

    async def _post(
        self,
        photo: FSInputFile | str,
        caption: str | None,
        chat_id: int,
        reply_id: int | None,
    ) -> Message:
        """提交一次照片请求"""
        return await self._bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_to_message_id=reply_id,
        )
