"""订阅与配额服务单元测试（ROADMAP V5.5）。"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.subscription import (
    ENTERPRISE_DAILY_LIMIT,
    FREE_DAILY_LIMIT,
    PRO_DAILY_LIMIT,
    TEAM_DAILY_LIMIT,
    SubscriptionError,
    SubscriptionService,
)


class SubscriptionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.service = SubscriptionService(
            path=Path(self._tmpdir.name) / "subscription.test.json",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_default_plan_is_free(self) -> None:
        self.assertEqual(self.service.plan, "free")
        snapshot = self.service.snapshot()
        self.assertEqual(snapshot["daily_limit"], FREE_DAILY_LIMIT)
        self.assertEqual(snapshot["daily_remaining"], FREE_DAILY_LIMIT)

    def test_consume_counts_usage(self) -> None:
        snapshot = self.service.consume()
        self.assertEqual(snapshot["daily_used"], 1)
        self.assertEqual(snapshot["daily_remaining"], FREE_DAILY_LIMIT - 1)

    def test_can_consume_until_limit(self) -> None:
        for _ in range(FREE_DAILY_LIMIT):
            self.assertTrue(self.service.can_consume())
            self.service.consume()
        self.assertFalse(self.service.can_consume())
        # 超限后 consume 仍继续（翻译不中断，尽力而为计量）
        snapshot = self.service.consume()
        self.assertEqual(snapshot["daily_used"], FREE_DAILY_LIMIT + 1)

    def test_set_plan_pro(self) -> None:
        snapshot = self.service.set_plan("pro")
        self.assertEqual(snapshot["plan"], "pro")
        self.assertEqual(snapshot["daily_limit"], PRO_DAILY_LIMIT)

    def test_set_plan_team(self) -> None:
        snapshot = self.service.set_plan("team")
        self.assertEqual(snapshot["plan"], "team")
        self.assertEqual(snapshot["daily_limit"], TEAM_DAILY_LIMIT)

    def test_set_plan_enterprise_unlimited(self) -> None:
        snapshot = self.service.set_plan("enterprise")
        self.assertEqual(snapshot["plan"], "enterprise")
        self.assertIsNone(snapshot["daily_limit"])
        self.assertTrue(self.service.can_consume())
        for _ in range(1000):
            self.service.consume()
        self.assertTrue(self.service.can_consume())

    def test_set_plan_invalid_rejected(self) -> None:
        with self.assertRaises(SubscriptionError):
            self.service.set_plan("gold")

    def test_reset_daily_usage(self) -> None:
        self.service.consume()
        self.service.consume()
        snapshot = self.service.reset_daily_usage()
        self.assertEqual(snapshot["daily_used"], 0)

    def test_persist_and_reload(self) -> None:
        self.service.consume()
        self.service.set_plan("pro")
        reloaded = SubscriptionService(
            path=Path(self._tmpdir.name) / "subscription.test.json",
        )
        snapshot = reloaded.snapshot()
        self.assertEqual(snapshot["plan"], "pro")
        self.assertEqual(snapshot["daily_used"], 1)

    def test_enterprise_limit_constant(self) -> None:
        self.assertIsNone(ENTERPRISE_DAILY_LIMIT)


if __name__ == "__main__":
    unittest.main()
