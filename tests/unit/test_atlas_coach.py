import unittest

from poe_trade.atlas import AtlasCoach, BuildMetric, CharacterState


class TestAtlasCoach(unittest.TestCase):
    def test_plan_prioritizes_gain_per_chaos(self) -> None:
        state = CharacterState(chaos=120.0, current_power=200.0, map_completion=50.0)
        candidates = [
            BuildMetric(name="fast", potential_gain=50.0, required_chaos=5.0, rank=2),
            BuildMetric(name="slow", potential_gain=70.0, required_chaos=7.0, rank=3),
        ]
        steps = AtlasCoach().plan(state, candidates)
        self.assertEqual(steps[0].name, "fast")
        self.assertEqual(steps[0].phase, "cheap")
        self.assertIn("phase=cheap", steps[0].rationale)
        self.assertEqual(steps[1].name, "slow")

    def test_plan_flags_conflicts(self) -> None:
        state = CharacterState(chaos=8.0, current_power=180.0, map_completion=25.0)
        candidates = [
            BuildMetric(name="alpha", potential_gain=10.0, required_chaos=1.0, rank=1),
            BuildMetric(name="beta", potential_gain=4.0, required_chaos=15.0, rank=1),
        ]
        steps = AtlasCoach().plan(state, candidates)
        self.assertEqual(steps[0].name, "alpha")
        self.assertEqual(steps[0].phase, "cheap")
        self.assertIn("confidence ok", steps[0].rationale)
        self.assertEqual(steps[-1].phase, "stretch")
        self.assertIn("budget exceeded", steps[-1].rationale)
