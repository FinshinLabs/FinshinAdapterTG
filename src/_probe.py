"""连接性探测

- 代理与 Token 两级探测，校验轮与诊断轮共用
- 构造期与请求期异常映射为字段错误，超时不上抛
"""

import asyncio
import re
from collections.abc import Awaitable, Callable

import aiohttp_socks
from aiohttp import ClientOSError

from finshin_sdk.domain import (
    ConfigKey,
    ConfigPath,
    ConfigSection,
    FieldKey,
    Platform,
)
from finshin_sdk.exceptions import (
    ConnectivityError,
    DirectTimeoutError,
    ProbeTimeoutError,
    ProxyAddressError,
    ProxyConnectionRefusedError,
    ProxyError,
    ProxySchemeError,
    ProxySchemeMissingError,
    ProxyTimeoutError,
    TelegramServerError,
    TokenError,
    TokenFormatError,
)

# 通道探测预算，与本体探测引擎各自持有
_PROBE_BUDGET = 9.0  # 秒
_PROBE_BUDGET_DIRECT = 3.0  # 直连被墙时必然等满，预算取短以快速失败

# 本适配器交出的代理项，探测错误表与面板标红共用同一身份
_PROXY_ITEM = ConfigKey.PROXY.path(f"adapter.{Platform.TELEGRAM}", ConfigSection.PROXY)

# 构造期异常消息里取协议名的规则
_SCHEME_RE = re.compile(r"Invalid scheme component:\s*(.*)", re.IGNORECASE)


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
        return TelegramServerError()

    if isinstance(e, aiohttp_socks.ProxyTimeoutError):
        return ProxyTimeoutError(proxy=proxy)

    if isinstance(e, (aiohttp_socks.ProxyError, aiohttp_socks.ProxyConnectionError)):
        return ProxyConnectionRefusedError(proxy=proxy)

    return ConnectivityError()


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
    return re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token.strip()) is not None


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
) -> dict[ConfigPath | str, Exception]:
    """双探测聚合

    - 代理先测，通过后再测令牌
    - 坏掉的字段交出异常本体，给人看的那句由校验侧取
    - 代理失败时只交代理错误
    """
    try:
        await probe(proxy)
    except ConnectivityError as e:
        return {_PROXY_ITEM: e}

    if not _is_token_wellformed(token):
        return {FieldKey.TOKEN: TokenFormatError()}

    errors: dict[ConfigPath | str, Exception] = {}
    try:
        await get_me(token, proxy)
    except TokenError as e:
        errors[FieldKey.TOKEN] = e
    except ConnectivityError as e:
        # getMe 阶段才暴露的网络问题归到 proxy
        errors[_PROXY_ITEM] = e

    return errors


async def attempt_channel(
    token: str, proxy: str
) -> tuple[str | None, dict[ConfigPath | str, Exception]]:
    """预算内探测单个通道

    - 轮次入口已在首帧前预触引擎，此处兜底漏触的直调方
    - 返回 (生效通道或 None, 坏掉字段的异常)
    - 空表即该通道通过
    - 超时预算按通道类型取值，直连短、代理长
    """
    preload_engine()
    errors: dict[ConfigPath | str, Exception] = {}
    try:
        errors = await asyncio.wait_for(
            _check_config(token, proxy),
            timeout=_PROBE_BUDGET_DIRECT if not proxy else _PROBE_BUDGET,
        )
    except TimeoutError:
        errors = {_PROXY_ITEM: ProbeTimeoutError()}
    if not errors:
        return proxy, {}
    return None, errors
