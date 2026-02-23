import json
import unittest

from poe_trade.atlas.models import Genome, GenomeGenerator


class GenomeTests(unittest.TestCase):
    def test_generator_is_deterministic_and_fingerprint_stable(self):
        generator = GenomeGenerator(seed=123)
        genome_a = generator.generate(base_class="Witch")
        genome_b = GenomeGenerator(seed=123).generate(base_class="Witch")
        self.assertEqual(genome_a.fingerprint(), genome_b.fingerprint())
        self.assertEqual(genome_a.to_json(), genome_b.to_json())
        restored = Genome.from_json(genome_a.to_json())
        self.assertEqual(restored.class_name, "Witch")
        self.assertGreaterEqual(restored.attributes["intelligence"], len(restored.auras) * 8 + 40)

    def test_non_witch_path_and_serialization_round_trip(self):
        generator = GenomeGenerator(seed=7)
        genome = generator.generate(base_class="Ranger")
        payload = genome.to_json()
        self.assertEqual(genome.class_name, "Ranger")
        self.assertIn(genome.ascendancy, GenomeGenerator.ASCENDANCIES["Ranger"])
        self.assertEqual(json.loads(payload)["main_skill"], genome.main_skill)
        self.assertEqual(Genome.from_json(payload).gear, genome.gear)
        self.assertGreaterEqual(genome.attributes["intelligence"], len(genome.auras) * 8 + 40)
