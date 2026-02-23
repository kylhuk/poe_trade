import unittest

from poe_trade.atlas.bench import (
    BenchCache,
    BenchEvaluator,
    Scenario,
    scenario_weights,
    survive_viability,
)
from poe_trade.atlas.models import GenomeGenerator


class BenchTests(unittest.TestCase):
    def test_evaluator_determinism_and_metrics(self):
        generator = GenomeGenerator(seed=99)
        genome = generator.generate()
        evaluator = BenchEvaluator()
        result_a = evaluator.evaluate(genome, Scenario.DEFENSE_CHECK)
        result_b = evaluator.evaluate(genome, Scenario.DEFENSE_CHECK)
        self.assertEqual(result_a.metrics.dps, result_b.metrics.dps)
        self.assertEqual(result_a.scenario, Scenario.DEFENSE_CHECK)
        self.assertIsInstance(result_a.viable, bool)

    def test_cache_returns_hits_and_misses(self):
        generator = GenomeGenerator(seed=17)
        genome = generator.generate()
        evaluator = BenchEvaluator()
        cache = BenchCache()
        result, miss = cache.lookup(genome, Scenario.MAP_CLEAR_BASELINE, evaluator)
        self.assertFalse(miss)
        cached, hit = cache.lookup(genome, Scenario.MAP_CLEAR_BASELINE, evaluator)
        self.assertTrue(hit)
        self.assertIs(cached, result)

    def test_budget_mapping_viability_breaks_on_strength(self):
        generator = GenomeGenerator(seed=12)
        genome = generator.generate()
        survival = 50.0
        constraint_balance = 0.5
        genome.attributes["strength"] = 65
        self.assertFalse(
            survive_viability(genome, Scenario.BUDGET_MAPPING, survival, constraint_balance)
        )
        genome.attributes["strength"] = 80
        self.assertTrue(
            survive_viability(genome, Scenario.BUDGET_MAPPING, survival, constraint_balance)
        )

    def test_budget_mapping_weights_diverge_from_boss(self):
        budget_weights = scenario_weights(Scenario.BUDGET_MAPPING)
        boss_weights = scenario_weights(Scenario.PINNACLE_BOSS)
        self.assertEqual(budget_weights["mana"], 1.0)
        self.assertNotEqual(budget_weights["mana"], boss_weights["mana"])
