from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TargetContract:
    name: str
    description: str
    recommendation_semantics: str
    required_label_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


TARGET_CONTRACT = TargetContract(
    name="execution-aware league price in chaos",
    description=(
        "v1 target for additive offline pricing in the isolated poe-ml tool surface"
    ),
    recommendation_semantics=(
        "recommended executable ask price expected to clear within 24h when "
        "sale_probability >= 0.5"
    ),
    required_label_fields=(
        "label_source",
        "label_quality",
        "as_of_ts",
        "league",
        "outlier_status",
    ),
)
