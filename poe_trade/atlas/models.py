from dataclasses import dataclass, field
from typing import Dict, List, Optional
import hashlib
import json
import random

@dataclass
class Genome:
    class_name: str
    ascendancy: Optional[str]
    main_skill: str
    supports: List[str]
    auras: List[str]
    passives: List[str]
    attributes: Dict[str, int]
    resists: Dict[str, int]
    gear: Dict[str, str]
    toggles: Dict[str, bool]

    def to_json(self) -> str:
        ordered = {
            "class_name": self.class_name,
            "ascendancy": self.ascendancy,
            "main_skill": self.main_skill,
            "supports": self.supports,
            "auras": self.auras,
            "passives": self.passives,
            "attributes": self.attributes,
            "resists": self.resists,
            "gear": self.gear,
            "toggles": self.toggles,
        }
        return json.dumps(ordered, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "Genome":
        data = json.loads(payload)
        return cls(
            class_name=data["class_name"],
            ascendancy=data.get("ascendancy"),
            main_skill=data["main_skill"],
            supports=data["supports"],
            auras=data["auras"],
            passives=data["passives"],
            attributes=data["attributes"],
            resists=data["resists"],
            gear=data["gear"],
            toggles=data["toggles"],
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()


@dataclass
class GenomeGenerator:
    seed: int
    rng: random.Random = field(init=False)

    CLASSES = ["Marauder", "Ranger", "Witch", "Duelist", "Templar", "Shadow"]
    ASCENDANCIES = {
        "Marauder": ["Juggernaut", "Berserker"],
        "Ranger": ["Deadeye", "Raider"],
        "Witch": ["Elementalist", "Occultist"],
        "Duelist": ["Champion", "Slayer"],
        "Templar": ["Inquisitor", "Hierophant"],
        "Shadow": ["Assassin", "Trickster"],
    }
    SKILLS = ["Blade Flurry", "Cyclone", "Fireball", "Arc", "Toxic Rain", "Summon Raging Spirit"]
    SUPPORTS = ["Concentrated Effect", "Awakened Empower", "Increased Critical Strikes", "Less Duration"]
    AURAS = ["Herald of Ash", "Haste", "Anger", "Determination", "Precision"]
    PASSIVES = [
        "Heart of the Warrior",
        "Painforged",
        "Arcane Focus",
        "Bloodless",
        "Survival Instincts",
        "Arcane Potency",
        "Champion's Fortitude",
    ]

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def generate(self, base_class: Optional[str] = None) -> Genome:
        chosen_class = base_class or self.rng.choice(self.CLASSES)
        ascendancies = self.ASCENDANCIES.get(chosen_class, [])
        ascendancy = self.rng.choice(ascendancies) if ascendancies else None
        main_skill = self.rng.choice(self.SKILLS)
        supports = self.rng.sample(self.SUPPORTS, k=2)
        auras = self.rng.sample(self.AURAS, k=2)
        passives = self.rng.sample(self.PASSIVES, k=3)

        base_attributes = {
            "strength": self.rng.randint(60, 120),
            "dexterity": self.rng.randint(40, 100),
            "intelligence": self.rng.randint(40, 110),
        }
        for key, minimum in ("strength", 70), ("dexterity", 50), ("intelligence", 50):
            base_attributes[key] = max(base_attributes[key], minimum)

        resists = {
            "fire": self.rng.randint(40, 80),
            "cold": self.rng.randint(40, 80),
            "lightning": self.rng.randint(40, 80),
        }
        for name in resists:
            resists[name] = min(resists[name], base_attributes["intelligence"] + 20)

        gear = {
            "weapon": f"{main_skill} Staff",
            "body_armour": f"{chosen_class} Plate",
            "helm": f"{ascendancy or chosen_class} Helm",
            "boots": "Fortified Boots",
            "accessory": "Veiled Ring",
        }

        toggles = {
            "map_clear": self.rng.choice([True, False]),
            "boss_focus": self.rng.choice([True, False]),
            "defensive_stance": self.rng.choice([True, False]),
        }
        reservation_load = len(auras) * 8
        if base_attributes["intelligence"] < reservation_load + 40:
            base_attributes["intelligence"] = reservation_load + 40

        return Genome(
            class_name=chosen_class,
            ascendancy=ascendancy,
            main_skill=main_skill,
            supports=supports,
            auras=auras,
            passives=passives,
            attributes=base_attributes,
            resists=resists,
            gear=gear,
            toggles=toggles,
        )
