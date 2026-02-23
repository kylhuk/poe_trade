from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from poe_trade.analytics.session_ledger import SessionSnapshot
from poe_trade.analytics.strategy_backtest import StrategyRegistry


class TestStrategyBacktest(unittest.TestCase):
    def test_builtin_definitions_include_all_strategies(self):
        definitions = StrategyRegistry.builtin_definitions()
        for index in range(1, 13):
            strategy_id = f"S{index:02d}"
            self.assertIn(strategy_id, definitions)
            definition = definitions[strategy_id]
            self.assertTrue(definition.title)
            self.assertTrue(definition.claim_summary)
            self.assertGreater(len(definition.tags), 0)
            self.assertGreater(len(definition.sources), 0)
            self.assertGreater(len(definition.required_inputs), 0)
            targets = definition.kpi_targets
            self.assertTrue(targets.profit_per_hour)
            self.assertTrue(targets.expected_value)
            self.assertTrue(targets.liquidity)
            self.assertTrue(targets.variance)

    def test_backtest_returns_kpi_summaries(self):
        now = datetime.now(timezone.utc)
        session = SessionSnapshot(
            session_id="session-a",
            realm="pc",
            league="Standard",
            start_snapshot="alpha",
            end_snapshot="omega",
            start_value=5.0,
            end_value=15.0,
            start_time=now - timedelta(hours=1),
            end_time=now,
        )
        stats = {
            "p50": 100.0,
            "spread": 30.0,
            "volatility": 5.0,
            "liquidity_score": 12.0,
            "listing_count": 8,
        }
        registry = StrategyRegistry.with_builtin_strategies()
        results = registry.backtest([session], stats)
        self.assertEqual(len(results), 12)
        for result in results:
            row = result.to_row()
            self.assertEqual(row["strategy_id"], result.definition.strategy_id)
            summary = row["kpi_summary"]
            self.assertGreaterEqual(summary["profit_per_hour"], 0.0)
            self.assertGreaterEqual(summary["expected_value"], 0.0)
            self.assertGreaterEqual(summary["liquidity"], 0.0)
            self.assertGreaterEqual(summary["variance"], 0.0)
            self.assertIsInstance(row["kpi_targets"], dict)


if __name__ == "__main__":
    unittest.main()
