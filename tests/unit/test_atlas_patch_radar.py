import unittest

from poe_trade.atlas import BuildSnapshot, compute_patch_delta


class TestPatchRadar(unittest.TestCase):
    def test_delta_severity_ordering(self) -> None:
        previous = [
            BuildSnapshot(name="Predator", power=150.0, rank=5, cost=10.0, meta_risk=2.0),
            BuildSnapshot(name="Hammer", power=120.0, rank=8, cost=7.0, meta_risk=1.5),
        ]
        current = [
            BuildSnapshot(name="Predator", power=160.0, rank=2, cost=12.0, meta_risk=2.5),
            BuildSnapshot(name="Hammer", power=130.0, rank=6, cost=7.5, meta_risk=1.6),
            BuildSnapshot(name="Scout", power=50.0, rank=10, cost=3.0, meta_risk=0.5),
        ]
        delta = compute_patch_delta(previous, current)
        self.assertEqual(delta[0].name, "Predator")
        self.assertEqual(delta[0].severity, "critical")
        self.assertEqual(delta[1].name, "Hammer")
        self.assertEqual(delta[1].severity, "major")
        self.assertEqual(delta[-1].severity, "stable")

    def test_delta_scoring_includes_cost_and_risk(self) -> None:
        previous = [BuildSnapshot(name="Scout", power=40.0, rank=12, cost=5.0, meta_risk=0.2)]
        current = [BuildSnapshot(name="Scout", power=50.0, rank=11, cost=8.0, meta_risk=0.8)]
        delta = compute_patch_delta(previous, current)
        self.assertAlmostEqual(delta[0].delta_power, 10.0)
        self.assertGreater(delta[0].delta_cost, 0)
        self.assertGreater(delta[0].delta_meta_risk, 0)
        self.assertLess(delta[0].delta_score, 6.0)
