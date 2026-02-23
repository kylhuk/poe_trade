import unittest

from poe_trade.atlas.bench import BenchEvaluator, BenchMetrics, BenchResult, Scenario
from poe_trade.atlas.models import GenomeGenerator
from poe_trade.atlas.ranking import (
    AtlasRowSerializer,
    compute_cost_distribution,
    compute_difficulty,
    compute_meta_risk,
    compute_power_scores,
)


class RankingTests(unittest.TestCase):
    def setUp(self):
        generator = GenomeGenerator(seed=2026)
        self.genome = generator.generate()
        # normalize resistances for predictable meta-risk
        self.genome.resists = {"fire": 90, "cold": 90, "lightning": 90}
        self.genome.attributes["intelligence"] = 100

    def test_numeric_formulas_and_reason_codes(self):
        metrics = BenchMetrics(dps=200.0, survival=150.0, mana_regen=60.0, constraint_balance=0.5)
        result = BenchResult(
            scenario=Scenario.DEFENSE_CHECK,
            metrics=metrics,
            viable=False,
            notes={"scenario_bonus": "defense"},
        )
        difficulty = compute_difficulty(result)
        self.assertEqual(difficulty.score, 80.0)
        self.assertListEqual(difficulty.reasons, ["reservation tight", "fails viability"])
        power = compute_power_scores(result)
        self.assertEqual(power.power, 130.0)
        self.assertEqual(power.value, 7.5)
        meta = compute_meta_risk(self.genome)
        self.assertAlmostEqual(meta.overcap_risk, 0.667, places=3)
        self.assertEqual(meta.reservation_risk, 0.0)

    def test_stable_reason_and_nonzero_reservation_risk(self):
        stable_metrics = BenchMetrics(
            dps=120.0,
            survival=200.0,
            mana_regen=50.0,
            constraint_balance=0.9,
        )
        stable_result = BenchResult(
            scenario=Scenario.MAP_CLEAR_BASELINE,
            metrics=stable_metrics,
            viable=True,
            notes={"scenario_bonus": "map"},
        )
        stable_difficulty = compute_difficulty(stable_result)
        self.assertListEqual(stable_difficulty.reasons, ["stable"])

        stressed_genome = GenomeGenerator(seed=11).generate(base_class="Templar")
        stressed_genome.attributes["intelligence"] = 10
        stressed_genome.auras = ["A", "B", "C", "D"]
        meta = compute_meta_risk(stressed_genome)
        self.assertGreater(meta.reservation_risk, 0.0)

    def test_atlas_row_serializer_alignment(self):
        evaluator = BenchEvaluator()
        benchmark = evaluator.evaluate(self.genome, Scenario.PINNACLE_BOSS)
        cost = compute_cost_distribution(self.genome)
        difficulty = compute_difficulty(benchmark)
        power = compute_power_scores(benchmark)
        meta = compute_meta_risk(self.genome)

        genome_row = AtlasRowSerializer.genome_row(self.genome)
        self.assertEqual(genome_row["build_id"], self.genome.fingerprint())
        self.assertIn("genome_json", genome_row)
        eval_row = AtlasRowSerializer.eval_row(self.genome, benchmark)
        self.assertEqual(eval_row["build_id"], self.genome.fingerprint())
        self.assertIn(eval_row["valid"], (0, 1))
        cost_row = AtlasRowSerializer.cost_row(self.genome, cost)
        cost_p10 = cost_row["cost_p10"]
        cost_p50 = cost_row["cost_p50"]
        cost_p90 = cost_row["cost_p90"]
        self.assertIsInstance(cost_p10, (int, float))
        self.assertIsInstance(cost_p50, (int, float))
        self.assertIsInstance(cost_p90, (int, float))
        if isinstance(cost_p10, (int, float)) and isinstance(cost_p50, (int, float)):
            self.assertGreaterEqual(cost_p50, cost_p10)
        if isinstance(cost_p50, (int, float)) and isinstance(cost_p90, (int, float)):
            self.assertGreaterEqual(cost_p90, cost_p50)
        breakdown = cost_row["breakdown"]
        self.assertIsInstance(breakdown, list)
        if isinstance(breakdown, list):
            self.assertTrue(all(isinstance(entry, str) for entry in breakdown))
        diff_row = AtlasRowSerializer.difficulty_row(self.genome, benchmark, difficulty)
        self.assertIn("reason_codes", diff_row)
        details_map = diff_row["details_map"]
        self.assertIsInstance(details_map, dict)
        if isinstance(details_map, dict):
            self.assertIsInstance(details_map.get("viable"), str)
        rank_row = AtlasRowSerializer.rank_row(self.genome, benchmark, power, meta)
        meta_risk = rank_row["meta_risk"]
        self.assertIsInstance(meta_risk, (int, float))
        if isinstance(meta_risk, (int, float)):
            self.assertEqual(meta_risk, max(meta.overcap_risk, meta.reservation_risk))
