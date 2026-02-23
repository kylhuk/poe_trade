from __future__ import annotations

import unittest

from poe_trade.analytics.forge_oracle import CraftAction, ForgeOracle


class TestForgeOracle(unittest.TestCase):
    def test_best_plan_returns_positive_ev(self):
        actions = (
            CraftAction(name="A", cost=1.0, value_gain=3.0),
            CraftAction(name="B", cost=2.0, value_gain=5.0),
        )
        oracle = ForgeOracle(actions)
        plan = oracle.best_plan(depth=2)
        self.assertIsNotNone(plan)
        opportunity = oracle.evaluate_plan("Standard", "item-1", 10.0, plan)
        self.assertGreater(opportunity.ev, 0)
        self.assertIn("A", opportunity.plan_id)


if __name__ == "__main__":
    unittest.main()
