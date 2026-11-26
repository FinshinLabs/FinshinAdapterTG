"""Telegram 字段归一取值

- 会话作用域、内容种类与发言人显示名按 Telegram 协议取
- 只交原文字与种类，占位标记由读取侧拼
- 容器段与引用目标换算成平台定位数字
"""

from aiogram.enums import ChatType, ContentType
from aiogram.types import Message, User

from finshin_sdk.domain import ChatScope, ContentKind
from finshin_sdk.domain.ids import ContainerCode, MessageId, UserId
from finshin_sdk.dto import MessageRefDTO

from ._config import PLATFORM

_ANONYMOUS_USER = UserId("unknown")  # 匿名代发无 user 段时的占位值
_GROUP_PREFIX = "g"  # 容器段的群聊前缀，私聊是 u


def scope_of(chat_type: str) -> ChatScope:
    """归一会话作用域

    - 频道一律归未知类型
    """
    match chat_type:
        case ChatType.PRIVATE:
            return ChatScope.PRIVATE
        case ChatType.GROUP | ChatType.SUPERGROUP:
            return ChatScope.GROUP
        case _:
            return ChatScope.UNKNOWN


def kind_of(content_type: str) -> ContentKind:
    """归一内容类型

    - 词表外的 Telegram 种类一律归未知类型
    - 语音条与音乐文件同归音频
    """
    match content_type:
        case ContentType.TEXT:
            return ContentKind.TEXT
        case ContentType.PHOTO:
            return ContentKind.PHOTO
        case ContentType.DOCUMENT:
            return ContentKind.DOCUMENT
        case ContentType.AUDIO | ContentType.VOICE:
            return ContentKind.AUDIO
        case ContentType.ANIMATION:
            return ContentKind.ANIMATION
        case ContentType.VIDEO:
            return ContentKind.VIDEO
        case _:
            return ContentKind.UNKNOWN


def display_name(message: Message) -> str:
    """取发言人显示名

    - 频道或匿名管理员代发时取来源群名
    """
    user = message.from_user
    if user is not None:
        return user.full_name or user.first_name or str(user.id)
    if message.sender_chat is not None:
        return message.sender_chat.title or ""
    return ""


def reply_text_of(reply: Message) -> str:
    """取被引用消息的正文文字

    - 只交文字，图片等种类另交一格
    """
    return reply.text or reply.caption or ""


def user_id_of(user: User | None) -> UserId:
    """取平台原始用户 id

    - 无用户信息时按占位值计，与主体键的用户段同形
    """
    return UserId(str(user.id)) if user is not None else _ANONYMOUS_USER


def sender_id(message: Message) -> UserId:
    """取发言人 id"""
    return user_id_of(message.from_user)


def build_ref(message: Message, container: ContainerCode) -> MessageRefDTO:
    """构造消息定位三元组"""
    return MessageRefDTO(
        platform=PLATFORM,
        container=container,
        message_id=MessageId(str(message.message_id)),
    )


def chat_id_of(container: ContainerCode) -> int:
    """容器段反推会话 id

    - 群聊 g 前缀补负号，私聊 u 前缀即用户 id
    """
    if not container:
        raise ValueError("容器段为空，无法定位会话")
    if container.startswith(_GROUP_PREFIX):
        return -int(container[1:])
    return int(container[1:])


def reply_id_of(ref: MessageRefDTO | None) -> int | None:
    """引用目标转消息 id"""
    return int(ref.message_id) if ref is not None else None
