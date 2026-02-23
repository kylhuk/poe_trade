import unittest

from poe_trade.ui.app import PAGE_REGISTRY, format_stash_export
from poe_trade.ui.client import LedgerApiClient


class UiPagesTest(unittest.TestCase):
    def test_page_registry_defines_all_names(self) -> None:
        expected = {
            "Market Overview",
            "Stash Pricer",
            "Flip Scanner",
            "Craft Advisor",
            "Farming ROI",
            "BuildAtlas",
            "Daily Plan",
            "Ops & Runtime",
        }
        self.assertTrue(expected.issubset(PAGE_REGISTRY.keys()))

    def test_local_client_shapes(self) -> None:
        client = LedgerApiClient(local_mode=True)
        overview = client.market_overview()
        self.assertTrue(overview)
        self.assertTrue(all("fp_loose" in row for row in overview))
        leaderboard = client.leaderboard()
        self.assertTrue(leaderboard.leaderboard)
        plan = client.advisor_daily_plan()
        self.assertTrue(hasattr(plan, "plan_items"))
        self.assertIsInstance(plan.plan_items, list)

    def test_ops_dashboard_shape(self) -> None:
        client = LedgerApiClient(local_mode=True)
        telemetry = client.ops_dashboard()
        self.assertGreater(telemetry.ingest_rate.public_stash_records_per_minute, 0)
        self.assertTrue(telemetry.rate_limit_alerts)
        self.assertIsInstance(telemetry.checkpoint_health, list)

    def test_format_stash_export_text(self) -> None:
        rows = [
            {"fp_loose": "divine", "league": "Sanctum", "count": 1, "estimate": 25.5},
            {"fp_loose": "essence", "league": "Sanctum", "count": 3, "estimate": 0.25},
        ]
        text = format_stash_export(rows)
        self.assertIn("divine", text)
        self.assertIn("essence", text)
