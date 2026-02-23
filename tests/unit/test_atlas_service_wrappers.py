import unittest

from poe_trade.services import atlas_bench, atlas_coach, atlas_forge


class AtlasServiceWrappersTest(unittest.TestCase):
    def test_forge_dry_run(self):
        atlas_forge.main(["--dry-run"])  # should exit after logging

    def test_bench_dry_run(self):
        atlas_bench.main(["--dry-run"])

    def test_coach_dry_run(self):
        atlas_coach.main(["--dry-run"])
