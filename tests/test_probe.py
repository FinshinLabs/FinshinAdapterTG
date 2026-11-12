"""Telegram 探测件测试

- _map_construct_error 把构造期 ValueError 与 UnicodeError 映射为精确异常
- scheme 为空时不得丢失提示
- _check_config 聚合 proxy 与 token 双探测，两坏同时报
- token 纯格式校验，坏 token 不联网即标记
"""

import asyncio
import sys
import unittest
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exceptions import describe_error  # noqa: E402
from finshin_adapter_tg import _probe as probe_mod  # noqa: E402
from finshin_sdk.domain import FieldKey  # noqa: E402
from finshin_sdk.exceptions import (  # noqa: E402
    ProxyAddressError,
    ProxySchemeError,
    ProxySchemeMissingError,
    TokenError,
)

_check_config = probe_mod._check_config
_map_construct_error = probe_mod._map_construct_error


class TestRealProbeNoHang(unittest.TestCase):
    """回归点

    - 真实 _probe_proxy 遇非法端口必须映射为业务异常，不上抛不挂死
    """

    def test_bad_port_maps_not_escapes(self) -> None:
        """非法端口的真实探测返回 proxy 键错误而非穿透"""
        from finshin_adapter_tg._probe import _check_config

        async def ok_get_me(token: str, proxy: str) -> None:
            return None

        errors = asyncio.run(
            _check_config("123:abc", "http://127.0.0.1:99999", get_me=ok_get_me)
        )
        self.assertIn("proxy", errors, "非法端口应产出 proxy 错误文案")


class TestMapConstructError(unittest.TestCase):
    """回归点

    - 异常消息携带有误（scheme 提取为空）
    """

    def test_empty_scheme_maps_to_missing(self) -> None:
        """协议位为空时另判一只，不拿占位文案填那格"""
        # proxy="aaa" 时 yarl 消息为 'Invalid scheme component: '（冒号后为空）
        mapped = _map_construct_error(ValueError("Invalid scheme component: "), "aaa")
        self.assertIsInstance(mapped, ProxySchemeMissingError)
        self.assertEqual(
            describe_error(mapped), "代理地址缺少 :// 协议头，收到的是 aaa"
        )

    def test_named_scheme_extracted(self) -> None:
        """具名非法协议被提取到异常属性"""
        e = ValueError("Invalid scheme component: ftp")
        mapped = _map_construct_error(e, "ftp://127.0.0.1:7890")
        self.assertIsInstance(mapped, ProxySchemeError)
        self.assertEqual(cast(ProxySchemeError, mapped).scheme, "ftp")

    def test_port_error_maps_to_address(self) -> None:
        """端口非法映射为地址错误"""
        mapped = _map_construct_error(
            ValueError("Invalid port component"), "http://127.0.0.1:99999"
        )
        self.assertIsInstance(mapped, ProxyAddressError)


class TestCheckConfig(unittest.IsolatedAsyncioTestCase):
    """回归点

    - 双探测聚合，token 与 proxy 问题同时上报
    """

    async def _ok_probe(self, proxy: str) -> None:
        return None

    async def _ok_get_me(self, token: str, proxy: str) -> None:
        return None

    async def test_all_good_returns_empty(self) -> None:
        """全通过返回空 dict"""
        errors = await _check_config(
            "123:abc",
            "http://127.0.0.1:7897",
            probe=self._ok_probe,
            get_me=self._ok_get_me,
        )
        self.assertEqual(errors, {})

    async def test_bad_token_marked(self) -> None:
        """远端拒绝时标记 token 字段"""

        async def bad_me(token: str, proxy: str) -> None:
            raise TokenError()

        errors = await _check_config(
            "123:abc",
            "http://127.0.0.1:7897",
            probe=self._ok_probe,
            get_me=bad_me,
        )
        self.assertIn(FieldKey.TOKEN, errors)

    async def test_bad_proxy_marks_proxy_only(self) -> None:
        """代理坏时只交代理一条，省掉那次 getMe"""

        async def dead_probe(proxy: str) -> None:
            raise ProxySchemeError(scheme="空", proxy=proxy)

        get_me_called = {"n": 0}

        async def counting_me(token: str, proxy: str) -> None:
            get_me_called["n"] += 1

        errors = await _check_config(
            "123:abc", "aaa", probe=dead_probe, get_me=counting_me
        )
        self.assertIn(FieldKey.PROXY, errors)
        self.assertEqual(list(errors), [FieldKey.PROXY], "暂未检测那一条归校验侧标注")
        self.assertEqual(get_me_called["n"], 0, "proxy 已坏不得再浪费一次 getMe")

    async def test_format_invalid_token_no_network(self) -> None:
        """格式非法 token 本地判定不联网"""
        # token 格式非法（无冒号）：probe 正常也不得调用 get_me，直接本地标记
        get_me_called = {"n": 0}

        async def counting_me(token: str, proxy: str) -> None:
            get_me_called["n"] += 1

        errors = await _check_config(
            "aaa",
            "http://127.0.0.1:7897",
            probe=self._ok_probe,
            get_me=counting_me,
        )
        self.assertIn(FieldKey.TOKEN, errors)
        self.assertEqual(get_me_called["n"], 0, "格式非法的 token 应本地判定，不联网")


if __name__ == "__main__":
    unittest.main()
