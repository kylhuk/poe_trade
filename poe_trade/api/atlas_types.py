from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass(frozen=True)
class AtlasBuildRecord:
    build_id: str
    name: str
    specialization: str
    node_count: int
    updated_at: datetime
    nodes: List[str]
    notes: str


@dataclass(frozen=True)
class AtlasRunRecord:
    run_id: str
    build_id: str
    generated_at: datetime
    node_count: int
    status: str
    scenario: str
    cost: float
    power: float
    meta_risk: float
