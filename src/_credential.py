"""Telegram 凭证声明

- 交出输入框名、提示、非法提示、凭证项与身份推导
"""

import re

from finshin_sdk import CredentialSpec
from finshin_sdk.domain import make_profile_key
from finshin_sdk.domain.config import ConfigPath

from ._config import PLATFORM, SOURCE

# Bot token 结构 bot_id:secret，冒号前即机器人数字 ID，重生成 token 不变
TOKEN_PATTERN = re.compile(r"(\d+):[A-Za-z0-9_-]+")


def _identity(token: str) -> str:
    """从 token 推导身份码

    - 结构非法返回空串
    """
    match = TOKEN_PATTERN.fullmatch(token.strip())
    return make_profile_key(PLATFORM, match.group(1)) if match else ""


CREDENTIAL = CredentialSpec(
    label="Bot Token",
    desc="从 @BotFather 获取，形如 123456:ABCDEF",
    invalid="Token 格式不正确\n应形如 123456:ABCDEF",
    item=ConfigPath(source=SOURCE, section="credential", key="token"),
    identity=_identity,
)
