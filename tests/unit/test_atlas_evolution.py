import random
import unittest

from poe_trade.atlas import Genome
from poe_trade.atlas.evolution import (
    crossover_genomes,
    evolve,
    mutate_genome,
    rank_population,
)


def _base_genome(name_suffix: str) -> Genome:
    return Genome(
        class_name="Marauder",
        ascendancy="Juggernaut",
        main_skill="Cyclone",
        supports=["Concentrated Effect", "Increased Critical Strikes"],
        auras=["Haste", "Determination"],
        passives=["Painforged", "Champion's Fortitude"],
        attributes={"strength": 80, "dexterity": 60, "intelligence": 70},
        resists={"fire": 60, "cold": 55, "lightning": 50},
        gear={
            "weapon": "Cyclone Staff",
            "body_armour": "Juggernaut Plate",
            "helm": "Juggernaut Helm",
            "boots": "Fortified Boots",
            "accessory": f"Veiled Ring {name_suffix}",
        },
        toggles={"map_clear": True, "boss_focus": False, "defensive_stance": True},
    )


class TestAtlasEvolution(unittest.TestCase):
    def setUp(self) -> None:
        self.base = _base_genome("alpha")
        self.peer = _base_genome("beta")

    def test_mutation_deterministic(self) -> None:
        mutated = mutate_genome(self.base, random.Random(42))
        self.assertEqual(mutated.attributes["strength"], 77)
        self.assertEqual(mutated.resists["cold"], 60)
        self.assertTrue(mutated.supports[1].endswith("+"))
        self.assertFalse(mutated.toggles["map_clear"])

    def test_crossover_computes_midpoint_attributes(self) -> None:
        child = crossover_genomes(self.base, self.peer, random.Random(1))
        self.assertEqual(child.main_skill, "Cyclone")
        self.assertEqual(child.supports, ["Concentrated Effect", "Increased Critical Strikes"])
        self.assertEqual(child.attributes["strength"], 80)
        self.assertEqual(child.resists["fire"], 60)

    def test_rank_population_exposes_components(self) -> None:
        ranked = rank_population([self.base, self.peer], random.Random(5), elite=2)
        self.assertEqual(len(ranked), 2)
        first = ranked[0]
        self.assertAlmostEqual(
            first.objective_score,
            first.power_component + first.survivability_component + first.novelty_bonus,
        )
        self.assertGreaterEqual(first.novelty_bonus, 0)

    def test_evolve_preserves_diversity(self) -> None:
        population = [self.base, self.peer]
        evolved = evolve(population, random.Random(7), target_size=4)
        self.assertEqual(len(evolved), 4)
        self.assertEqual(len({entry.fingerprint() for entry in evolved}), 4)
