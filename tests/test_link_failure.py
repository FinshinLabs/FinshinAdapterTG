"""Telegram 链路故障判定测试

- 连接层异常算断连，服务端应答与程序 bug 不算
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError  # noqa: E402
from aiogram.methods import GetMe  # noqa: E402
from aiohttp import ClientError  # noqa: E402
from aiohttp_socks import (  # noqa: E402
    ProxyConnectionError,
    ProxyError,
    ProxyTimeoutError,
)

from finshin_adapter_tg._session import is_link_failure  # noqa: E402


class TestIsLinkFailure(unittest.TestCase):
    """链路层判定"""

    LINK = (
        ProxyConnectionError("x"),
        ProxyTimeoutError("x"),
        ProxyError("x"),
        ClientError("x"),
        TelegramNetworkError(method=GetMe(), message="x"),
        ConnectionRefusedError("x"),
    )
    SERVER_OR_BUG = (
        TelegramBadRequest(method=GetMe(), message="x"),
        TypeError("x"),
        ValueError("x"),
    )

    def test_connection_errors_count_as_link_failure(self) -> None:
        for exc in self.LINK:
            with self.subTest(type(exc).__name__):
                self.assertTrue(is_link_failure(exc))

    def test_server_answers_and_bugs_do_not(self) -> None:
        for exc in self.SERVER_OR_BUG:
            with self.subTest(type(exc).__name__):
                self.assertFalse(is_link_failure(exc))


if __name__ == "__main__":
    unittest.main()
