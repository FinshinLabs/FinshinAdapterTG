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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finshin_adapter_tg import _probe as probe_mod  # noqa: E402
from finshin_adapter_tg._credential import CREDENTIAL  # noqa: E402
from finshin_adapter_tg._errors import (  # noqa: E402
    ProxyAddressError,
    ProxyConnectionRefusedError,
    ProxySchemeError,
    ProxySchemeMissingError,
    TokenError,
)
from finshin_sdk.domain import RowStatus  # noqa: E402

_check_config = probe_mod._check_config
_map_construct_error = probe_mod._map_construct_error
_PROXY_ITEM = probe_mod.PROXY_ITEM


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
        self.assertIn(_PROXY_ITEM, errors, "非法端口应产出 proxy 错误文案")


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
            probe_mod._describe(mapped), "代理地址缺少 :// 协议头，收到的是 aaa"
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
        self.assertIn(CREDENTIAL.item, errors)

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
        self.assertIn(_PROXY_ITEM, errors)
        self.assertEqual(list(errors), [_PROXY_ITEM], "暂未检测那一条归校验侧标注")
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
        self.assertIn(CREDENTIAL.item, errors)
        self.assertEqual(get_me_called["n"], 0, "格式非法的 token 应本地判定，不联网")


class TestRunChannel(unittest.IsolatedAsyncioTestCase):
    """回归点

    - 通道通即交生效地址，token 错也算通道通
    - 代理类错误换成交出者那句文案，超时归代理项
    """

    async def test_pass_reports_effective(self) -> None:
        """全通过交生效地址与空错误表"""

        async def ok(token: str, proxy: str) -> dict:
            return {}

        with (
            patch.object(probe_mod, "_check_config", ok),
            patch.object(probe_mod, "preload_engine"),
            patch.object(probe_mod, "note"),
        ):
            result = await probe_mod.run_channel("123:abc", "http://127.0.0.1:7897", 5)

        self.assertTrue(result.accepted)
        self.assertEqual(result.effective, "http://127.0.0.1:7897")
        self.assertEqual(result.field_errors, {})

    async def test_proxy_error_not_accepted(self) -> None:
        """代理类错误交文案且不算通道通过"""

        async def dead(token: str, proxy: str) -> dict:
            return {_PROXY_ITEM: ProxyConnectionRefusedError(proxy=proxy)}

        with (
            patch.object(probe_mod, "_check_config", dead),
            patch.object(probe_mod, "preload_engine"),
            patch.object(probe_mod, "note"),
        ):
            result = await probe_mod.run_channel("123:abc", "http://127.0.0.1:7897", 5)

        self.assertFalse(result.accepted)
        self.assertIsNone(result.effective)
        self.assertIn("无法连接到代理服务器", result.field_errors[_PROXY_ITEM])

    async def test_token_error_keeps_channel_accepted(self) -> None:
        """token 错只报字段错，通道本身算通"""

        async def bad_token(token: str, proxy: str) -> dict:
            return {CREDENTIAL.item: TokenError()}

        with (
            patch.object(probe_mod, "_check_config", bad_token),
            patch.object(probe_mod, "preload_engine"),
            patch.object(probe_mod, "note"),
        ):
            result = await probe_mod.run_channel("123:abc", "", 5)

        self.assertTrue(result.accepted)
        self.assertEqual(result.field_errors, {CREDENTIAL.item: "Token 无效"})

    async def test_budget_timeout_maps_to_proxy_text(self) -> None:
        """预算耗尽按代理项超时交结果，不上抛"""

        async def slow(token: str, proxy: str) -> dict:
            await asyncio.sleep(1)
            return {}

        with (
            patch.object(probe_mod, "_check_config", slow),
            patch.object(probe_mod, "preload_engine"),
            patch.object(probe_mod, "note"),
        ):
            result = await probe_mod.run_channel("123:abc", "", 0.01)

        self.assertFalse(result.accepted)
        self.assertIn("验证超时", result.field_errors[_PROXY_ITEM])


class TestProxySection(unittest.TestCase):
    """回归点

    - 代理地址的显隐由字段级条件交出，窗口不点名字段
    """

    def test_defaults_and_visibility(self) -> None:
        """模式默认自动，代理项只在自动与仅配置两档可见"""
        from finshin_adapter_tg import _config

        fields = {field.key: field for field in _config._PROXY_SECTION.fields}
        self.assertEqual(fields["proxy_mode"].default, "auto")
        self.assertEqual(fields["proxy_mode"].options, ("auto", "cfg", "sys", "direct"))
        self.assertEqual(fields["proxy"].default, "")
        condition = fields["proxy"].visible_when[0]
        self.assertEqual(condition.key, "proxy_mode")
        visible = {
            mode: mode in condition.values for mode in fields["proxy_mode"].options
        }
        self.assertEqual(
            visible, {"auto": True, "cfg": True, "sys": False, "direct": False}
        )


class TestBuildPlan(unittest.IsolatedAsyncioTestCase):
    """回归点

    - 自动档按配置、系统、直连排，缺席行不给通道
    - 单路档只排选定一路，缺地址即缺席轮
    - 配置与系统同端点时系统行标跳过
    """

    def _plan(self, mode: str, cfg: str = "", system: str | None = None):
        from finshin_adapter_tg import _plan

        return _plan.build_connection_plan(
            {"proxy": {"proxy_mode": mode, "proxy": cfg}},
            "123:abc",
            system_proxy=system,
        )

    def test_auto_orders_three_rows(self) -> None:
        """自动档三行按配置、系统、直连排"""
        plan = self._plan("auto", "http://127.0.0.1:7897", "http://127.0.0.1:7890")
        self.assertEqual([row.row_id for row in plan.rows], ["cfg", "sys", "direct"])
        self.assertEqual([ch.row_id for ch in plan.channels], ["cfg", "sys", "direct"])

    def test_auto_absent_rows_have_no_channel(self) -> None:
        """缺席的配置与系统行直接给终态，不发探测"""
        plan = self._plan("auto")
        self.assertEqual(
            [row.status for row in plan.rows],
            [RowStatus.FAIL, RowStatus.FAIL, RowStatus.PENDING],
        )
        self.assertEqual([ch.row_id for ch in plan.channels], ["direct"])

    def test_same_endpoint_skips_system(self) -> None:
        """配置与系统同端点时系统行标跳过"""
        addr = "http://127.0.0.1:7890"
        plan = self._plan("auto", addr, addr)
        self.assertEqual(plan.rows[1].status, RowStatus.SKIP)
        self.assertEqual([ch.row_id for ch in plan.channels], ["cfg", "direct"])

    def test_single_cfg_absent_settles_on_proxy_row(self) -> None:
        """仅配置档留空即缺席，红点落代理项"""
        from finshin_sdk.domain import ProbeOutcome

        plan = self._plan("cfg")
        self.assertEqual(plan.channels, ())
        verdict = plan.finish(ProbeOutcome())
        self.assertEqual(list(verdict.field_errors), [_PROXY_ITEM])

    def test_direct_mode_budget_shorter(self) -> None:
        """直连通道预算短于代理通道"""
        plan = self._plan("direct", "http://127.0.0.1:7897")
        self.assertEqual([ch.row_id for ch in plan.channels], ["direct"])
        self.assertLess(plan.channels[0].budget, 9.0)


if __name__ == "__main__":
    unittest.main()
