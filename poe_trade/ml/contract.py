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


@dataclass(frozen=True)
class PromotionContract:
    metric_name: str
    coverage_floor: float
    min_mdape_improvement: float
    protected_cohort_max_regression: float
    hotspot_top_n: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationContract:
    name: str
    split_kind: str
    supported_splits: tuple[str, ...]
    primary_metric: str
    verdict_enums: tuple[str, ...]
    loop_status_enums: tuple[str, ...]
    promotion: PromotionContract

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["promotion"] = self.promotion.to_dict()
        return payload


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


MIRAGE_EVAL_CONTRACT = EvaluationContract(
    name="mirage_eval_contract_v1",
    split_kind="rolling",
    supported_splits=("rolling",),
    primary_metric="mdape",
    verdict_enums=("promote", "hold"),
    loop_status_enums=(
        "completed",
        "failed_gates",
        "stopped_no_improvement",
        "stopped_budget",
    ),
    promotion=PromotionContract(
        metric_name="mdape",
        coverage_floor=0.75,
        min_mdape_improvement=0.005,
        protected_cohort_max_regression=0.02,
        hotspot_top_n=12,
    ),
)
