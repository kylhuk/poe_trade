import unittest

from poe_trade.atlas import (
    allocate_templates_by_slot,
    build_template_from_vector,
    deterministic_budget_selector,
)


class TestRareTemplates(unittest.TestCase):
    def test_template_is_deterministic(self) -> None:
        first = build_template_from_vector([1.0, 2.0, 3.0], "alpha", 2)
        second = build_template_from_vector([1.0, 2.0, 3.0], "alpha", 2)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.price_distribution["low"], 15.0)
        self.assertEqual(first.price_distribution["median"], 4.0)
        self.assertAlmostEqual(first.liquidity["velocity"], 0.821, places=3)

    def test_budget_selector_prefers_budget_match(self) -> None:
        template_a = build_template_from_vector([1.0, 2.0, 3.0], "alpha", 1)
        template_b = build_template_from_vector([4.0, 5.0, 6.0], "bravo", 2)
        result = deterministic_budget_selector([template_a, template_b], 10)
        self.assertEqual(result.id, template_b.id)

        result_low = deterministic_budget_selector([template_a, template_b], 5)
        self.assertEqual(result_low.id, template_a.id)

        result_tiny = deterministic_budget_selector([template_a, template_b], 1)
        self.assertEqual(result_tiny.id, template_a.id)

    def test_allocator_reports_unmet_constraints(self) -> None:
        weapon = build_template_from_vector([1.0, 2.0, 3.0], "weapon", 1)
        armour = build_template_from_vector([4.0, 5.0, 6.0], "armour", 2)
        accessory = build_template_from_vector([0.5, 0.5, 0.5], "accessory", 3)
        slots = {
            "weapon": [weapon],
            "armour": [armour],
            "accessory": [accessory],
        }
        liquidity = {"weapon": 1.2, "armour": 0.8, "accessory": 1.0}
        allocation = allocate_templates_by_slot(slots, total_budget=12.0, liquidity_preference=liquidity)
        self.assertEqual(allocation.selection["weapon"].id, weapon.id)
        self.assertEqual(allocation.selection["armour"].id, armour.id)
        self.assertIn("armour budget_exceeded", allocation.unmet_constraints[0])
        self.assertTrue(any(entry.startswith("total_budget_exceeded") for entry in allocation.unmet_constraints))
        self.assertEqual(allocation.total_cost, 15.0)
