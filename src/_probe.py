"""连接性探测

- 代理与 Token 两级探测，校验轮与诊断轮共用
- 构造期与请求期异常映射为字段错误，超时不上抛
- 探测结果在适配器内换成给人看的那句话
"""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp_socks
from aiohttp import ClientOSError

from finshin_sdk.domain import ProbeResult
from finshin_sdk.domain.config import ConfigPath
from finshin_sdk.exceptions import (
    ConnectivityError,
    ProbeCrashedError,
    ProbeTimeoutError,
    ServerUnreachableError,
)

from ._config import SOURCE
from ._credential import CREDENTIAL, TOKEN_PATTERN
from ._errors import (
    DirectTimeoutError,
    ProxyAddressError,
    ProxyConnectionRefusedError,
    ProxyError,
    ProxySchemeError,
    ProxySchemeMissingError,
    ProxyTimeoutError,
    TokenError,
    TokenFormatError,
)
from ._log import note
from ._messages import ConnectionMessage

# 本适配器交出的代理项，探测错误与面板标红共用同一身份
PROXY_ITEM = ConfigPath(source=SOURCE, section="proxy", key="proxy")

# 异常到文案的映射，沿继承链取最近的一条
_TEXTS: dict[type, str] = {
    TokenError: ConnectionMessage.TOKEN_INVALID,
    TokenFormatError: ConnectionMessage.TOKEN_MALFORMED,
    ProbeTimeoutError: ConnectionMessage.TIMEOUT,
    ProbeCrashedError: ConnectionMessage.CRASH,
    ServerUnreachableError: ConnectionMessage.SERVER_UNREACHABLE,
    DirectTimeoutError: ConnectionMessage.DIRECT_TIMEOUT,
    ProxyError: ConnectionMessage.PROXY_INVALID,
    ProxySchemeError: ConnectionMessage.SCHEME_UNSUPPORTED,
    ProxySchemeMissingError: ConnectionMessage.SCHEME_MISSING,
    ProxyAddressError: ConnectionMessage.ADDRESS_UNPARSABLE,
    ProxyConnectionRefusedError: ConnectionMessage.PROXY_REFUSED,
    ProxyTimeoutError: ConnectionMessage.PROXY_TIMEOUT,
}

# 构造期异常消息里取协议名的规则
_SCHEME_RE = re.compile(r"Invalid scheme component:\s*(.*)", re.IGNORECASE)


def _describe(exc: BaseException) -> str:
    """取异常那句给人看的话

    - 沿继承链往上找最近的一句文案
    - 表里没有即报异常类名
    """
    attrs: dict[str, Any] = vars(exc)
    for cls in type(exc).__mro__:
        template = _TEXTS.get(cls)
        if template is None:
            continue
        try:
            return template.format(**attrs)
        except (KeyError, IndexError):
            return template
    return type(exc).__name__


def _map_construct_error(e: Exception, proxy: str) -> ConnectivityError:
    """映射构造期异常"""
    if isinstance(e, UnicodeError):
        # idna 域名标签非法（如 192..168.1.1）
        return ProxyAddressError(proxy=proxy)

    msg = str(e)
    m = _SCHEME_RE.search(msg)
    if m:
        scheme = m.group(1).strip()
        if not scheme:
            return ProxySchemeMissingError(proxy=proxy)
        return ProxySchemeError(scheme=scheme, proxy=proxy)

    if "port" in msg.lower():
        return ProxyAddressError(proxy=proxy)

    return ProxyError(proxy=proxy)


def _map_request_error(e: Exception, proxy: str) -> ConnectivityError:
    """映射请求期异常"""
    from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError

    # 子类分支必须排在父类前
    if isinstance(e, TelegramUnauthorizedError):
        return TokenError()

    if isinstance(e, TelegramNetworkError):
        if not proxy:
            # 无代理的网络错误属于直连不通，与代理无关
            return DirectTimeoutError()
        if isinstance(e.__cause__, ClientOSError):
            return ProxyConnectionRefusedError(proxy=proxy)
        return ServerUnreachableError()

    if isinstance(e, aiohttp_socks.ProxyTimeoutError):
        return ProxyTimeoutError(proxy=proxy)

    if isinstance(e, (aiohttp_socks.ProxyError, aiohttp_socks.ProxyConnectionError)):
        return ProxyConnectionRefusedError(proxy=proxy)

    return ProbeCrashedError()


async def _probe_proxy(proxy: str) -> None:
    """纯代理探测

    - 构造期异常映射为业务异常
    """
    from ._session import SSLUnverifiedSession

    try:
        SSLUnverifiedSession(proxy=proxy)
    except (ValueError, UnicodeError) as e:
        raise _map_construct_error(e, proxy) from e


async def _get_me(token: str, proxy: str) -> None:
    """探测 Token 有效性

    - 失败抛连接性异常
    """
    from aiogram import Bot

    from ._session import SSLUnverifiedSession

    bot: Bot | None = None
    try:
        # 探测轮的成败属配置校验不属引擎链路，喂进断连状态机会误弹计时框
        session = SSLUnverifiedSession(proxy=proxy, report_link=False)
        bot = Bot(token=token, session=session)
        await bot.get_me()
    except TimeoutError as e:
        # 无代理时超时是直连不通，不能报"连接代理超时"的空地址文案
        raise (ProxyTimeoutError(proxy=proxy) if proxy else DirectTimeoutError()) from e
    except (ValueError, UnicodeError) as e:
        # 构造期异常穿透兜底（正常流程已在 _probe_proxy 拦截）
        raise _map_construct_error(e, proxy) from e
    except Exception as e:
        raise _map_request_error(e, proxy) from e
    finally:
        if bot is not None:
            try:
                await bot.session.close()
            except Exception:
                pass


def _is_token_wellformed(token: str) -> bool:
    """本地校验 Token 结构"""
    return TOKEN_PATTERN.fullmatch(token.strip()) is not None


def preload_engine() -> None:
    """预触引擎导入链

    - 须在轮次首帧点亮通道行之前调用
    """
    # aiogram 经 PEP 562 懒加载，首触约 5 秒同步导入会饿死 wait_for 与界面倒计时
    from aiogram import Bot as _Bot  # noqa: F401

    from ._session import SSLUnverifiedSession as _Session  # noqa: F401


async def _check_config(
    token: str,
    proxy: str,
    probe: Callable[[str], Awaitable[None]] = _probe_proxy,
    get_me: Callable[[str, str], Awaitable[None]] = _get_me,
) -> dict[ConfigPath, Exception]:
    """双探测聚合

    - 代理先测，通过后再测令牌
    - 坏掉的字段交出异常本体
    - 代理失败时只交代理错误
    """
    try:
        await probe(proxy)
    except ConnectivityError as e:
        return {PROXY_ITEM: e}

    if not _is_token_wellformed(token):
        return {CREDENTIAL.item: TokenFormatError()}

    errors: dict[ConfigPath, Exception] = {}
    try:
        await get_me(token, proxy)
    except TokenError as e:
        errors[CREDENTIAL.item] = e
    except ConnectivityError as e:
        # getMe 阶段才暴露的网络问题归到 proxy
        errors[PROXY_ITEM] = e

    return errors


async def run_channel(token: str, proxy: str, budget: float) -> ProbeResult:
    """预算内探测单个通道

    - 轮次入口已在首帧前预触引擎，此处兜底漏触的直调方
    - 通道通即交生效地址，token 错也算通道通
    - 代理类错误换成文案随结果交出
    """
    preload_engine()
    started = time.monotonic()
    try:
        errors = await asyncio.wait_for(_check_config(token, proxy), timeout=budget)
    except TimeoutError:
        errors = {PROXY_ITEM: ProbeTimeoutError()}
    except Exception:
        # 探测自己崩了，按兜底行报检查异常
        errors = {PROXY_ITEM: ProbeCrashedError()}
    via = (
        ConnectionMessage.VIA_DIRECT
        if not proxy
        else ConnectionMessage.VIA_PROXY.format(proxy=proxy)
    )
    note(ConnectionMessage.COST.format(via=via, cost=time.monotonic() - started))
    if not errors:
        return ProbeResult(accepted=True, effective=proxy)
    texts = {key: _describe(value) for key, value in errors.items()}
    return ProbeResult(
        accepted=PROXY_ITEM not in errors,
        field_errors=texts,
    )
