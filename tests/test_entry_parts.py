"""入口交出六件的契约

- 装配只交运行时，运行时带清单编译器、中间件挂载点与路由落点
- 凭证声明带输入框名与身份推导
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finshin_adapter_tg import entry  # noqa: E402
from finshin_sdk import AdapterParts, BaseAdapter  # noqa: E402


class TestEntryParts(unittest.TestCase):
    """入口模块的装配契约"""

    def test_parts_hands_over_runtime_only(self) -> None:
        """装配结果带挂载口与编译器"""
        parts = entry.parts()
        self.assertIsInstance(parts, AdapterParts)
        runtime = parts.assemble("123456:AA-test-token", None)
        self.assertIsInstance(runtime, BaseAdapter)
        self.assertTrue(callable(runtime.router_builder))
        self.assertTrue(callable(runtime.attach_middleware))
        self.assertTrue(hasattr(runtime, "route_sink"))

    def test_parts_hands_over_credential(self) -> None:
        """凭证声明带输入框名与身份推导"""
        credential = entry.parts().credential
        self.assertEqual(credential.label, "Bot Token")
        self.assertEqual(credential.identity("123456:AA-test-token"), "tg.123456")
        self.assertEqual(credential.identity("not-a-token"), "")


if __name__ == "__main__":
    unittest.main()
