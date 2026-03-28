from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingRegressor,
    RandomForestRegressor,
    StackingRegressor,
)
from sklearn.feature_extraction import DictVectorizer
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import ElasticNet, HuberRegressor, QuantileRegressor
from sklearn.neighbors import KNeighborsRegressor

try:
    from catboost import CatBoostRegressor
except ImportError:
    CatBoostRegressor = cast(Any, None)

try:
    from lightgbm import LGBMRegressor
except ImportError:
    LGBMRegressor = cast(Any, None)

try:
    import lightgbm as lgb
except ImportError:
    lgb = cast(Any, None)

try:
    from xgboost import XGBRegressor
except ImportError:
    XGBRegressor = cast(Any, None)

from ..contract import PRICING_BENCHMARK_CONTRACT
from .features import (
    build_base_identity_key,
    build_fast_sale_feature_row,
    build_feature_row,
    build_item_state_key,
    validate_ring_parser_row,
)
from .routes import assign_cohort
from .sql import (
    BENCHMARK_EXTRACT_COLUMNS,
    BENCHMARK_EXTRACT_TABLE,
    BENCHMARK_FORBIDDEN_FEATURE_PATTERNS,
    ITEM_FAMILY_NAMES,
    build_pricing_benchmark_extract_query,
    pricing_benchmark_contract_spec,
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _support_bucket(sample_count: int) -> str:
    if sample_count >= 2_000:
        return "xl"
    if sample_count >= 500:
        return "l"
    if sample_count >= 100:
        return "m"
    if sample_count >= 20:
        return "s"
    return "xs"


def _sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("as_of_ts") or ""),
        str(row.get("identity_key") or row.get("item_id") or ""),
        str(row.get("item_id") or ""),
    )


def _group_key(row: Mapping[str, Any]) -> str:
    return str(row.get("identity_key") or row.get("item_id") or "")


def _feature_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return build_feature_row(row)


def _mirage_feature_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    feature_row = build_feature_row(row)
    allowed_keys = {
        "ilvl",
        "corrupted",
        "fractured",
        "synthesised",
        "support_count_recent",
    }
    return {
        key: value
        for key, value in feature_row.items()
        if key in allowed_keys
        or key.endswith("_present")
        or key.endswith("_quality_roll")
    }


def _fast_sale_feature_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return build_fast_sale_feature_row(row)


def _lgbm_neo_feature_frame(rows: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    return frame


def _lgbm_neo_group_key(frame: pd.DataFrame) -> tuple[str, pd.Series]:
    if (
        "item_fingerprint" in frame.columns
        and cast(Any, frame["item_fingerprint"]).notna().any()
    ):
        source = cast(Any, frame["item_fingerprint"])
        return "item_fingerprint", source.where(
            source.notna(), cast(Any, frame["item_id"])
        )
    return "item_id", cast(Any, frame["item_id"])


def _lgbm_neo_split_frame(
    frame: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
    pd.Series,
    dict[str, Any],
]:
    frame_df = cast(pd.DataFrame, frame)
    if "item_id" not in frame_df.columns:
        raise ValueError("lgbm-neo frame requires item_id")
    if "observed_at" not in frame_df.columns:
        raise ValueError("lgbm-neo frame requires observed_at")
    if "price_chaos" not in frame_df.columns:
        raise ValueError("lgbm-neo frame requires price_chaos")

    frame_df = frame_df.copy()
    frame_df["_observed_at"] = pd.to_datetime(
        cast(Any, frame_df["observed_at"]), utc=True, errors="coerce"
    )
    if bool(cast(Any, frame_df["_observed_at"].isna().any())):
        raise ValueError("lgbm-neo frame requires valid observed_at values")

    group_field, group_source = _lgbm_neo_group_key(frame_df)
    frame_df["_lgbm_neo_group_key"] = group_source.fillna("").astype(str)

    ordered = cast(
        pd.DataFrame,
        frame_df.sort_values(
            ["_observed_at", "_lgbm_neo_group_key", "item_id"],
            kind="mergesort",
        ),
    )

    grouped_frames: list[tuple[pd.Timestamp, str, pd.DataFrame]] = []
    for group_key, group in ordered.groupby(
        "_lgbm_neo_group_key", sort=False, dropna=False
    ):
        group_frame = cast(pd.DataFrame, group).copy()
        first_seen = cast(pd.Timestamp, group_frame["_observed_at"].min())
        grouped_frames.append((first_seen, str(group_key), group_frame))

    grouped_frames.sort(key=lambda item: (item[0], item[1]))
    total_groups = len(grouped_frames)
    if total_groups < 3:
        raise ValueError("lgbm-neo split requires at least three ordered groups")

    train_end = max(1, min(total_groups - 2, int(total_groups * 0.6)))
    validation_end = max(
        train_end + 1,
        min(total_groups - 1, int(total_groups * 0.8)),
    )
    if validation_end >= total_groups:
        validation_end = total_groups - 1

    train_groups = grouped_frames[:train_end]
    validation_groups = grouped_frames[train_end:validation_end]
    test_groups = grouped_frames[validation_end:]

    if not validation_groups:
        validation_groups = [train_groups.pop()]
    if not test_groups:
        test_groups = [validation_groups.pop()]

    def _concat_groups(
        groups: Sequence[tuple[pd.Timestamp, str, pd.DataFrame]],
    ) -> pd.DataFrame:
        return cast(
            pd.DataFrame,
            pd.concat([group for _, _, group in groups], axis=0),
        )

    def _finalize(
        split_frame: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.Series, dict[str, str | int]]:
        y = np.log1p(cast(Any, split_frame["price_chaos"]).astype("float32"))
        feature_frame = cast(
            pd.DataFrame,
            split_frame.drop(
                columns=[
                    "item_id",
                    "observed_at",
                    "item_fingerprint",
                    "price_chaos",
                    "_observed_at",
                    "_lgbm_neo_group_key",
                ],
                errors="ignore",
            ),
        )
        return (
            feature_frame,
            cast(pd.Series, y),
            {
                "rows": int(len(split_frame)),
                "observed_at_start": split_frame["_observed_at"].min().isoformat(),
                "observed_at_end": split_frame["_observed_at"].max().isoformat(),
            },
        )

    train_frame, y_train, train_meta = _finalize(_concat_groups(train_groups))
    valid_frame, y_valid, valid_meta = _finalize(_concat_groups(validation_groups))
    test_frame, y_test, test_meta = _finalize(_concat_groups(test_groups))

    return (
        train_frame,
        valid_frame,
        test_frame,
        y_train,
        y_valid,
        y_test,
        {
            "kind": "grouped_forward",
            "group_field": group_field,
            "train_rows": train_meta["rows"],
            "validation_rows": valid_meta["rows"],
            "test_rows": test_meta["rows"],
            "train_groups": len(train_groups),
            "validation_groups": len(validation_groups),
            "test_groups": len(test_groups),
            "train_strategy": f"ordered by observed_at, grouped by {group_field}",
            "validation_strategy": f"next ordered {group_field} window",
            "test_strategy": f"final ordered {group_field} window",
            "train_observed_at_start": train_meta["observed_at_start"],
            "train_observed_at_end": train_meta["observed_at_end"],
            "validation_observed_at_start": valid_meta["observed_at_start"],
            "validation_observed_at_end": valid_meta["observed_at_end"],
            "test_observed_at_start": test_meta["observed_at_start"],
            "test_observed_at_end": test_meta["observed_at_end"],
        },
    )


def _lgbm_neo_prepare_features(
    X_train: pd.DataFrame, X_valid: pd.DataFrame, X_test: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    categorical_columns: list[str] = []

    for column in list(X_train.columns):
        if column.startswith("tier_"):
            X_train = X_train.drop(columns=[column])
            X_valid = X_valid.drop(columns=[column])
            X_test = X_test.drop(columns=[column])
            continue
        if column.startswith("val_"):
            X_train[column] = X_train[column].astype("float32")
            X_valid[column] = X_valid[column].astype("float32")
            X_test[column] = X_test[column].astype("float32")
        elif column.startswith("has_"):
            X_train[column] = X_train[column].astype("uint8")
            X_valid[column] = X_valid[column].astype("uint8")
            X_test[column] = X_test[column].astype("uint8")
        elif column in {"ilvl", "corrupted", "fractured", "synthesised"}:
            X_train[column] = X_train[column].astype("float32")
            X_valid[column] = X_valid[column].astype("float32")
            X_test[column] = X_test[column].astype("float32")
        elif (
            pd.api.types.is_object_dtype(X_train[column])
            or pd.api.types.is_string_dtype(X_train[column])
            or pd.api.types.is_categorical_dtype(X_train[column])
        ):
            combined = pd.concat(
                [X_train[column], X_valid[column], X_test[column]], ignore_index=True
            )
            unique_values = combined.dropna().astype(str).unique().tolist()
            if len(unique_values) <= 1:
                X_train = X_train.drop(columns=[column])
                X_valid = X_valid.drop(columns=[column])
                X_test = X_test.drop(columns=[column])
                continue
            categories = pd.Index(unique_values)
            X_train[column] = pd.Categorical(
                X_train[column].astype("string"), categories=categories
            )
            X_valid[column] = pd.Categorical(
                X_valid[column].astype("string"), categories=categories
            )
            X_test[column] = pd.Categorical(
                X_test[column].astype("string"), categories=categories
            )
            categorical_columns.append(column)

    return X_train, X_valid, X_test, categorical_columns


def _encode_lgbm_neo_categorical_features_for_fallback(
    X_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    categorical_columns: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    for column in categorical_columns:
        combined = pd.concat(
            [X_train[column], X_valid[column], X_test[column]], ignore_index=True
        )
        categories = pd.Index(combined.astype("string").dropna().unique().tolist())
        X_train[column] = pd.Categorical(
            X_train[column].astype("string"), categories=categories
        ).codes.astype("float32")
        X_valid[column] = pd.Categorical(
            X_valid[column].astype("string"), categories=categories
        ).codes.astype("float32")
        X_test[column] = pd.Categorical(
            X_test[column].astype("string"), categories=categories
        ).codes.astype("float32")
    return X_train, X_valid, X_test


def _normalize_affix_token_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1]
    return " ".join(text.split()).lower()


@dataclass(frozen=True)
class MirageAffixCatalog:
    pattern_to_family: dict[str, str]
    family_bounds: dict[str, tuple[float, float]]


_AFFIX_SIGNATURE_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_AFFIX_ROLL_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _snake_case_mod_base_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", text).replace("__", "_")
    return "_".join(part for part in snake.lower().split("_") if part)


def _affix_signature(value: Any) -> str:
    text = _normalize_affix_token_text(value)
    text = text.replace("{n}", " ")
    text = _AFFIX_SIGNATURE_NUMBER_PATTERN.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = text.replace("(", " ").replace(")", " ")
    text = text.replace("[", " ").replace("]", " ")
    text = text.replace("-", " ")
    text = " ".join(text.split())
    return text


def _affix_roll_value(value: Any) -> float:
    numbers = [
        float(number) for number in _AFFIX_ROLL_NUMBER_PATTERN.findall(str(value or ""))
    ]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def build_mirage_affix_catalog(rows: Sequence[Mapping[str, Any]]) -> MirageAffixCatalog:
    pattern_to_family: dict[str, str] = {}
    family_bounds: dict[str, tuple[float, float]] = {}
    for row in rows:
        signature = _affix_signature(row.get("mod_text_pattern"))
        family = _snake_case_mod_base_name(row.get("mod_base_name"))
        if not signature or not family:
            continue
        pattern_to_family.setdefault(signature, family)
        value = _to_float(row.get("mod_max_value"), 0.0)
        if family not in family_bounds:
            family_bounds[family] = (value, value)
        else:
            lower, upper = family_bounds[family]
            family_bounds[family] = (min(lower, value), max(upper, value))
    return MirageAffixCatalog(
        pattern_to_family=pattern_to_family, family_bounds=family_bounds
    )


def _mirage_affix_quality_roll(
    *, affix_text: Any, catalog: MirageAffixCatalog
) -> tuple[str | None, float | None]:
    signature = _affix_signature(affix_text)
    family = catalog.pattern_to_family.get(signature)
    if not family:
        return None, None

    lower, upper = catalog.family_bounds.get(family, (0.0, 0.0))
    if upper <= lower:
        return family, 1.0

    value = _affix_roll_value(affix_text)
    roll = (value - lower) / (upper - lower)
    return family, max(0.0, min(1.0, roll))


def normalize_mirage_iron_ring_branch_row(
    row: Mapping[str, Any], *, affix_catalog: MirageAffixCatalog
) -> dict[str, Any]:
    normalized = dict(row)
    affixes = normalized.pop("affixes", []) or []
    mod_features: dict[str, float] = {}
    for affix in affixes:
        if not isinstance(affix, (tuple, list)) or len(affix) != 2:
            continue
        family, quality_roll = _mirage_affix_quality_roll(
            affix_text=affix[1], catalog=affix_catalog
        )
        if not family or quality_roll is None:
            continue
        mod_features[f"{family}_present"] = 1.0
        mod_features[f"{family}_quality_roll"] = max(
            quality_roll, mod_features.get(f"{family}_quality_roll", 0.0)
        )

    parsed_amount = _to_float(normalized.get("target_price_chaos"), 0.0)
    normalized["mod_features_json"] = json.dumps(mod_features, separators=(",", ":"))
    normalized["target_price_chaos"] = max(0.1, parsed_amount)
    normalized["target_fast_sale_24h_price"] = max(0.1, parsed_amount * 0.95)
    normalized["target_sale_probability_24h"] = 1.0
    normalized["target_likely_sold"] = 1
    normalized["sale_confidence_flag"] = 1
    normalized["label_weight"] = 1.0
    normalized["label_source"] = "branch_mirage_iron_ring_v1"

    if "affix_count" in normalized:
        normalized["mod_token_count"] = _to_int(normalized.get("affix_count"), 0)

    cohort = assign_cohort(normalized)
    normalized.update(
        {
            "strategy_family": cohort["strategy_family"],
            "cohort_key": cohort["cohort_key"],
            "parent_cohort_key": cohort["parent_cohort_key"],
            "material_state_signature": cohort["material_state_signature"],
            "item_state_key": build_item_state_key(normalized),
            "base_identity_key": build_base_identity_key(normalized),
        }
    )
    validate_ring_parser_row(normalized)
    return normalized


def _row_target(row: Mapping[str, Any]) -> float:
    target_price_divine = _to_float(row.get("target_price_divine"), 0.0)
    if target_price_divine > 0:
        return max(0.1, target_price_divine)
    return max(0.1, _to_float(row.get("target_price_chaos"), 0.0))


def _row_weight(row: Mapping[str, Any]) -> float:
    label_weight = max(0.1, _to_float(row.get("label_weight"), 0.25))
    sale_confidence = 0.45 + 0.55 * max(
        0.0, min(1.0, _to_float(row.get("sale_confidence_flag"), 0.0))
    )
    return max(0.1, label_weight * sale_confidence)


def _log1p_price_targets(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    return np.log1p(np.asarray([_row_target(row) for row in rows], dtype=float))


def _censored_log1p_price_targets(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    values: list[float] = []
    for row in rows:
        actual_price = _row_target(row)
        fast_sale_floor = max(
            actual_price,
            max(
                0.1,
                _to_float(
                    row.get("target_fast_sale_24h_price_divine"),
                    _to_float(row.get("target_fast_sale_24h_price"), actual_price),
                ),
            ),
        )
        sale_confidence = _to_float(row.get("sale_confidence_flag"), 0.0)
        weak_label_multiplier = 0.70 + (0.30 * sale_confidence)
        values.append(max(actual_price, fast_sale_floor * weak_label_multiplier))
    return np.log1p(np.asarray(values, dtype=float))


def _validate_row(row: Mapping[str, Any]) -> None:
    route = str(row.get("route") or "").strip().lower()
    if route and route not in PRICING_BENCHMARK_CONTRACT.non_exchange_routes:
        raise ValueError(f"benchmark row routes must stay non-exchange; got {route!r}")
    for key in row:
        text = str(key)
        if (
            text.startswith("future_")
            or text.startswith("post_cutoff_")
            or "future" in text
        ):
            raise ValueError(f"benchmark row leaks future-derived field {text!r}")


def validate_benchmark_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("benchmark rows are required")
    for row in rows:
        _validate_row(row)


def split_benchmark_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> dict[str, list[dict[str, Any]]]:
    validate_benchmark_rows(rows)
    ordered = [dict(row) for row in sorted(rows, key=_sort_key)]
    total = len(ordered)
    if total < 3:
        raise ValueError("benchmark requires at least three rows for a forward split")

    train_end = max(1, min(total - 2, int(total * train_fraction)))
    validation_end = max(
        train_end + 1,
        min(total - 1, int(total * (train_fraction + validation_fraction))),
    )
    if validation_end >= total:
        validation_end = total - 1

    train_rows = ordered[:train_end]
    validation_rows = ordered[train_end:validation_end]
    test_rows = ordered[validation_end:]

    if not validation_rows:
        validation_rows = [train_rows.pop()]
    if not test_rows:
        test_rows = [validation_rows.pop()]

    return {
        "train": train_rows,
        "validation": validation_rows,
        "test": test_rows,
    }


def split_grouped_forward_benchmark_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> dict[str, list[dict[str, Any]]]:
    validate_benchmark_rows(rows)
    grouped_rows: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(rows, key=_sort_key):
        grouped_rows.setdefault(_group_key(row), []).append(dict(row))

    ordered_groups = sorted(
        grouped_rows.values(),
        key=lambda group: (
            str(group[0].get("as_of_ts") or ""),
            _group_key(group[0]),
        ),
    )
    total_groups = len(ordered_groups)
    if total_groups < 3:
        raise ValueError(
            "benchmark requires at least three identity groups for a grouped forward split"
        )

    train_end = max(1, min(total_groups - 2, int(total_groups * train_fraction)))
    validation_end = max(
        train_end + 1,
        min(
            total_groups - 1, int(total_groups * (train_fraction + validation_fraction))
        ),
    )
    if validation_end >= total_groups:
        validation_end = total_groups - 1

    train_groups = ordered_groups[:train_end]
    validation_groups = ordered_groups[train_end:validation_end]
    test_groups = ordered_groups[validation_end:]

    if not validation_groups:
        validation_groups = [train_groups.pop()]
    if not test_groups:
        test_groups = [validation_groups.pop()]

    def _flatten(groups: Sequence[Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        for group in groups:
            flat.extend(dict(row) for row in group)
        return flat

    return {
        "train": _flatten(train_groups),
        "validation": _flatten(validation_groups),
        "test": _flatten(test_groups),
    }


def split_grouped_forward_benchmark_rows_by_field(
    rows: Sequence[Mapping[str, Any]],
    *,
    group_field: str,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> dict[str, list[dict[str, Any]]]:
    validate_benchmark_rows(rows)
    grouped_rows: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(rows, key=_sort_key):
        grouped_rows.setdefault(str(row.get(group_field) or ""), []).append(dict(row))

    ordered_groups = sorted(
        grouped_rows.values(),
        key=lambda group: (
            str(group[0].get("as_of_ts") or ""),
            str(group[0].get(group_field) or ""),
        ),
    )
    total_groups = len(ordered_groups)
    if total_groups < 3:
        raise ValueError(
            f"benchmark requires at least three groups for field {group_field!r}"
        )

    train_end = max(1, min(total_groups - 2, int(total_groups * train_fraction)))
    validation_end = max(
        train_end + 1,
        min(
            total_groups - 1, int(total_groups * (train_fraction + validation_fraction))
        ),
    )
    if validation_end >= total_groups:
        validation_end = total_groups - 1

    train_groups = ordered_groups[:train_end]
    validation_groups = ordered_groups[train_end:validation_end]
    test_groups = ordered_groups[validation_end:]

    if not validation_groups:
        validation_groups = [train_groups.pop()]
    if not test_groups:
        test_groups = [validation_groups.pop()]

    def _flatten(groups: Sequence[Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        for group in groups:
            flat.extend(dict(row) for row in group)
        return flat

    return {
        "train": _flatten(train_groups),
        "validation": _flatten(validation_groups),
        "test": _flatten(test_groups),
    }


def _dense_feature_matrix(
    rows: Sequence[Mapping[str, Any]],
    *,
    vectorizer: DictVectorizer | None = None,
    feature_builder: Callable[[Mapping[str, Any]], dict[str, Any]] = _feature_dict,
) -> tuple[DictVectorizer, np.ndarray]:
    feature_rows = [feature_builder(row) for row in rows]
    fitted = vectorizer or DictVectorizer(sparse=False)
    X = fitted.fit_transform(feature_rows)
    return fitted, np.asarray(X, dtype=float)


def _transform_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    vectorizer: DictVectorizer,
    feature_builder: Callable[[Mapping[str, Any]], dict[str, Any]] = _feature_dict,
) -> np.ndarray:
    feature_rows = [feature_builder(row) for row in rows]
    X = vectorizer.transform(feature_rows)
    return np.asarray(X, dtype=float)


def _fit_model(
    model: Any, X: np.ndarray, y: np.ndarray, *, sample_weight: np.ndarray | None
) -> Any:
    if sample_weight is None:
        try:
            model.fit(X, y)
            return model
        except Exception:
            fallback = DummyRegressor(strategy="mean")
            fallback.fit(X, y)
            return fallback
    try:
        model.fit(X, y, sample_weight=sample_weight)
        return model
    except TypeError:
        try:
            model.fit(X, y)
            return model
        except Exception:
            fallback = DummyRegressor(strategy="mean")
            fallback.fit(X, y)
            return fallback
    except Exception:
        fallback = DummyRegressor(strategy="mean")
        fallback.fit(X, y)
        return fallback


def _predict_price(
    model: Any,
    X: np.ndarray,
    *,
    residual_low: float,
    residual_high: float,
) -> dict[str, np.ndarray]:
    pred_log = np.asarray(model.predict(X), dtype=float)
    p50 = np.maximum(0.1, np.expm1(pred_log))
    p10 = np.maximum(0.1, np.expm1(pred_log + residual_low))
    p90 = np.maximum(p50, np.expm1(pred_log + residual_high))
    return {"p10": p10, "p50": p50, "p90": p90}


def _metrics_from_predictions(
    rows: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    actuals = np.asarray([_row_target(row) for row in rows], dtype=float)
    p10 = np.asarray(predictions["p10"], dtype=float)
    p50 = np.asarray(predictions["p50"], dtype=float)
    p90 = np.asarray(predictions["p90"], dtype=float)
    ape = np.abs(p50 - actuals) / np.maximum(actuals, 0.01)
    abs_errors = np.abs(p50 - actuals)
    log_errors = np.square(np.log1p(p50) - np.log1p(actuals))
    interval_hits = (p10 <= actuals) & (actuals <= p90)
    return {
        "sample_count": len(rows),
        "mdape": float(_median([float(value) for value in ape])),
        "wape": float(abs_errors.sum() / max(float(actuals.sum()), 0.01)),
        "rmsle": float(math.sqrt(float(log_errors.mean()))),
        "interval_80_coverage": float(interval_hits.mean()),
        "predicted_prices": p50.tolist(),
    }


def _tail_metrics_from_predictions(
    rows: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, np.ndarray],
    *,
    tail_quantile: float = 0.9,
) -> dict[str, Any]:
    actuals = np.asarray([_row_target(row) for row in rows], dtype=float)
    if not len(actuals):
        return {
            "sample_count": 0,
            "tail_quantile": tail_quantile,
            "tail_threshold": 0.0,
            "mdape": 0.0,
            "wape": 0.0,
            "rmsle": 0.0,
            "interval_80_coverage": 0.0,
        }
    tail_threshold = float(np.quantile(actuals, tail_quantile))
    tail_indexes = [int(index) for index in np.flatnonzero(actuals >= tail_threshold)]
    if not tail_indexes:
        tail_indexes = list(range(len(actuals)))
    tail_rows = [rows[index] for index in tail_indexes]
    tail_predictions = {
        name: np.asarray(values, dtype=float)[tail_indexes]
        for name, values in predictions.items()
    }
    tail_metrics = _metrics_from_predictions(tail_rows, tail_predictions)
    tail_metrics.pop("predicted_prices", None)
    return {
        **tail_metrics,
        "sample_count": len(tail_rows),
        "tail_quantile": tail_quantile,
        "tail_threshold": tail_threshold,
    }


def _slice_metrics(
    rows: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, np.ndarray],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        bucket = _support_bucket(_to_int(row.get("support_count_recent"), 0))
        buckets.setdefault(bucket, []).append(index)
    metrics: dict[str, dict[str, Any]] = {}
    for bucket, indexes in buckets.items():
        bucket_rows = [rows[index] for index in indexes]
        bucket_predictions = {
            name: np.asarray(values, dtype=float)[indexes]
            for name, values in predictions.items()
        }
        bucket_metrics = _metrics_from_predictions(bucket_rows, bucket_predictions)
        bucket_metrics.pop("predicted_prices", None)
        metrics[bucket] = bucket_metrics
    return metrics


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    description: str
    model_factory: Callable[[], Any]
    target_builder: Callable[[Sequence[Mapping[str, Any]]], np.ndarray] = (
        _log1p_price_targets
    )
    uses_sample_weight: bool = False
    weak_label_note: str = ""
    target_name: str = "log1p_price"


def _fast_sale_log1p_price_targets(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    return np.log1p(
        np.asarray(
            [
                max(
                    0.1,
                    _to_float(
                        row.get("target_fast_sale_24h_price_divine"),
                        _to_float(row.get("target_fast_sale_24h_price"), 0.0),
                    ),
                )
                for row in rows
            ],
            dtype=float,
        )
    )


def _elasticnet_model() -> ElasticNet:
    return ElasticNet(alpha=0.0005, l1_ratio=0.35, max_iter=6000, random_state=42)


def _huber_model() -> HuberRegressor:
    return HuberRegressor(alpha=0.0001, epsilon=1.35, max_iter=1000)


def _catboost_model() -> Any:
    if CatBoostRegressor is None:
        return RandomForestRegressor(
            n_estimators=250,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=1,
        )
    return CatBoostRegressor(
        iterations=300,
        depth=6,
        learning_rate=0.05,
        loss_function="RMSE",
        random_seed=42,
        verbose=False,
    )


def _lightgbm_model() -> Any:
    if LGBMRegressor is None:
        return HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_depth=6,
            max_iter=300,
            random_state=42,
        )
    return LGBMRegressor(
        n_estimators=350,
        learning_rate=0.05,
        max_depth=6,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        n_jobs=1,
        verbosity=-1,
    )


def _fast_sale_lightgbm_model() -> Any:
    if LGBMRegressor is None:
        return HistGradientBoostingRegressor(
            learning_rate=0.0141472921986667,
            max_depth=9,
            max_iter=335,
            min_samples_leaf=48,
            random_state=42,
        )
    return LGBMRegressor(
        objective="regression",
        n_estimators=335,
        learning_rate=0.0141472921986667,
        num_leaves=221,
        max_depth=9,
        min_child_samples=48,
        subsample=0.7483192096930324,
        colsample_bytree=0.9707059955394408,
        reg_alpha=0.1657011797146675,
        reg_lambda=2.2987089737123103,
        min_split_gain=0.4434141988273311,
        random_state=42,
        n_jobs=1,
        verbosity=-1,
    )


def _xgboost_model() -> Any:
    if XGBRegressor is None:
        return HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_depth=6,
            max_iter=300,
            random_state=42,
        )
    return XGBRegressor(
        n_estimators=350,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=1,
        objective="reg:squarederror",
        verbosity=0,
    )


def _quantile_model() -> QuantileRegressor:
    return QuantileRegressor(quantile=0.5, alpha=0.0001, solver="highs")


def _censored_quantile_model() -> QuantileRegressor:
    return QuantileRegressor(quantile=0.5, alpha=0.0001, solver="highs")


def _censored_forest_model() -> Any:
    from sklearn.ensemble import RandomForestRegressor

    return RandomForestRegressor(
        n_estimators=350,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=1,
    )


def _knn_model() -> KNeighborsRegressor:
    return KNeighborsRegressor(n_neighbors=5, weights="distance")


def _stacked_ensemble_model() -> Any:
    class _SafeStackingRegressor:
        def __init__(self) -> None:
            self._model: Any | None = None
            self._fallback = ElasticNet(
                alpha=0.0005, l1_ratio=0.5, max_iter=6000, random_state=42
            )

        def fit(
            self,
            X: np.ndarray,
            y: np.ndarray,
            sample_weight: np.ndarray | None = None,
        ) -> "_SafeStackingRegressor":
            if len(X) < 3:
                self._model = self._fallback
                _fit_model(self._fallback, X, y, sample_weight=sample_weight)
                return self

            estimators = [
                ("elasticnet", _elasticnet_model()),
                ("huber", _huber_model()),
                ("catboost", _catboost_model()),
                ("lightgbm", _lightgbm_model()),
                ("xgboost", _xgboost_model()),
            ]
            stacked = StackingRegressor(
                estimators=estimators,
                final_estimator=ElasticNet(
                    alpha=0.0005, l1_ratio=0.5, max_iter=6000, random_state=42
                ),
                passthrough=True,
                cv=min(3, len(X)),
                n_jobs=1,
            )
            fitted = _fit_model(stacked, X, y, sample_weight=sample_weight)
            if not hasattr(fitted, "estimators_"):
                fitted = _fit_model(self._fallback, X, y, sample_weight=sample_weight)
            self._model = fitted
            return self

        def predict(self, X: np.ndarray) -> np.ndarray:
            if self._model is None:
                raise RuntimeError("stacked ensemble has not been fitted yet")
            return np.asarray(self._model.predict(X), dtype=float)

    return _SafeStackingRegressor()


BENCHMARK_CANDIDATE_SPECS: tuple[CandidateSpec, ...] = (
    CandidateSpec(
        name="elasticnet_log",
        description="Regularized linear baseline on log price",
        model_factory=_elasticnet_model,
    ),
    CandidateSpec(
        name="huber_log",
        description="Robust Huber regression on log price",
        model_factory=_huber_model,
    ),
    CandidateSpec(
        name="catboost_log",
        description="CatBoost regressor on frozen features",
        model_factory=_catboost_model,
    ),
    CandidateSpec(
        name="lightgbm_log",
        description="LightGBM gradient boosting baseline",
        model_factory=_lightgbm_model,
    ),
    CandidateSpec(
        name="xgboost_log",
        description="XGBoost gradient boosting baseline",
        model_factory=_xgboost_model,
    ),
    CandidateSpec(
        name="quantile_regressor_log",
        description="Median quantile regression",
        model_factory=_quantile_model,
    ),
    CandidateSpec(
        name="censored_quantile_log",
        description="Tobit-inspired censored quantile regression",
        model_factory=_censored_quantile_model,
        target_builder=_censored_log1p_price_targets,
        uses_sample_weight=True,
        weak_label_note="censored at fast_sale_24h_price with sale_confidence weighting",
        target_name="censored_log1p_price",
    ),
    CandidateSpec(
        name="censored_forest_log",
        description="Censored random forest benchmark",
        model_factory=_censored_forest_model,
        target_builder=_censored_log1p_price_targets,
        uses_sample_weight=True,
        weak_label_note="censored at fast_sale_24h_price with sale_confidence weighting",
        target_name="censored_log1p_price",
    ),
    CandidateSpec(
        name="knn_log",
        description="Nearest-neighbor retrieval baseline",
        model_factory=_knn_model,
    ),
    CandidateSpec(
        name="stacked_ensemble_log",
        description="Stacked ensemble over the strongest single-model baselines",
        model_factory=_stacked_ensemble_model,
    ),
)


def _candidate_metadata(spec: CandidateSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "prediction_space": "log1p_price",
        "target_name": spec.target_name,
        "weak_label_note": spec.weak_label_note,
    }


def _train_candidate(
    spec: CandidateSpec,
    split: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    tail_quantile: float | None = None,
    feature_builder: Callable[[Mapping[str, Any]], dict[str, Any]] = _feature_dict,
) -> dict[str, Any]:
    train_rows = split["train"]
    validation_rows = split["validation"]
    test_rows = split["test"]

    vectorizer, train_matrix = _dense_feature_matrix(
        train_rows, feature_builder=feature_builder
    )
    validation_matrix = _transform_rows(
        validation_rows, vectorizer=vectorizer, feature_builder=feature_builder
    )
    test_matrix = _transform_rows(
        test_rows, vectorizer=vectorizer, feature_builder=feature_builder
    )

    y_train = np.asarray(spec.target_builder(train_rows), dtype=float)
    sample_weight = (
        np.asarray([_row_weight(row) for row in train_rows], dtype=float)
        if spec.uses_sample_weight
        else None
    )

    model = spec.model_factory()
    if isinstance(model, KNeighborsRegressor):
        neighbor_count = _to_int(
            getattr(model, "n_neighbors", len(train_rows)), len(train_rows)
        )
        model.n_neighbors = max(1, min(neighbor_count, len(train_rows)))
    model = _fit_model(model, train_matrix, y_train, sample_weight=sample_weight)

    train_pred_log = np.asarray(model.predict(train_matrix), dtype=float)
    residuals = y_train - train_pred_log
    residual_low, residual_high = np.quantile(residuals, [0.10, 0.90])
    if residual_low > residual_high:
        residual_low, residual_high = residual_high, residual_low

    validation_predictions = _predict_price(
        model,
        validation_matrix,
        residual_low=float(residual_low),
        residual_high=float(residual_high),
    )
    test_predictions = _predict_price(
        model,
        test_matrix,
        residual_low=float(residual_low),
        residual_high=float(residual_high),
    )

    validation_metrics = _metrics_from_predictions(
        validation_rows, validation_predictions
    )
    test_metrics = _metrics_from_predictions(test_rows, test_predictions)

    validation_slice_metrics = _slice_metrics(validation_rows, validation_predictions)
    test_slice_metrics = _slice_metrics(test_rows, test_predictions)

    if tail_quantile is not None:
        validation_metrics["tail_metrics"] = _tail_metrics_from_predictions(
            validation_rows,
            validation_predictions,
            tail_quantile=tail_quantile,
        )
        test_metrics["tail_metrics"] = _tail_metrics_from_predictions(
            test_rows,
            test_predictions,
            tail_quantile=tail_quantile,
        )

    return {
        "candidate": spec.name,
        "metadata": _candidate_metadata(spec),
        "vectorizer": vectorizer,
        "model": model,
        "residual_interval": {
            "low": float(residual_low),
            "high": float(residual_high),
        },
        "validation": {
            **validation_metrics,
            "slice_metrics": validation_slice_metrics,
        },
        "test": {
            **test_metrics,
            "slice_metrics": test_slice_metrics,
        },
    }


def _candidate_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate": str(result.get("candidate") or ""),
        "metadata": result.get("metadata") or {},
        "residual_interval": result.get("residual_interval") or {},
        "validation": result.get("validation") or {},
        "test": result.get("test") or {},
    }


def _sold_only_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sold_rows = [
        dict(row)
        for row in rows
        if _to_int(row.get("target_likely_sold"), 0) > 0
        or _to_int(row.get("sale_confidence_flag"), 0) > 0
    ]
    return sold_rows or [dict(row) for row in rows]


def benchmark_contract() -> dict[str, Any]:
    contract = pricing_benchmark_contract_spec()
    contract.update(
        {
            "benchmark_table": BENCHMARK_EXTRACT_TABLE,
            "allowed_columns": list(BENCHMARK_EXTRACT_COLUMNS),
            "candidate_count": len(BENCHMARK_CANDIDATE_SPECS),
            "split_kind": "forward",
            "price_units": ["chaos", "divine"],
            "weak_label_policy": {
                "confirmation_horizon_hours": PRICING_BENCHMARK_CONTRACT.confirmation_horizon_hours,
                "sale_confidence_weighting": "label_weight * sale_confidence_flag",
                "non_exchange_routes": list(
                    PRICING_BENCHMARK_CONTRACT.non_exchange_routes
                ),
            },
        }
    )
    return contract


FAST_SALE_BENCHMARK_CANDIDATE_SPECS: tuple[CandidateSpec, ...] = (
    CandidateSpec(
        name="catboost_fast_sale_log",
        description="CatBoost baseline on fast-sale log price",
        model_factory=_catboost_model,
        target_builder=_fast_sale_log1p_price_targets,
        target_name="fast_sale_24h_log1p_price",
    ),
    CandidateSpec(
        name="lightgbm_fast_sale_log",
        description="LightGBM fast-sale log-price model with scientist params",
        model_factory=_fast_sale_lightgbm_model,
        target_builder=_fast_sale_log1p_price_targets,
        uses_sample_weight=True,
        weak_label_note="sale_confidence weighting is applied to the fast-sale target",
        target_name="fast_sale_24h_log1p_price",
    ),
    CandidateSpec(
        name="stacked_ensemble_fast_sale_log",
        description="Stacked ensemble with residual correction on fast-sale log price",
        model_factory=_stacked_ensemble_model,
        target_builder=_fast_sale_log1p_price_targets,
        uses_sample_weight=True,
        weak_label_note="ensemble candidate with residual correction on fast-sale target",
        target_name="fast_sale_24h_log1p_price",
    ),
)


def fast_sale_benchmark_contract() -> dict[str, Any]:
    contract = pricing_benchmark_contract_spec()
    contract.update(
        {
            "name": "fast_sale_24h_price_benchmark_v1",
            "benchmark_name": "fast_sale_24h_price_benchmark_v1",
            "benchmark_table": "jsonl:iron_ring_wide_10k",
            "target_name": "target_fast_sale_24h_price",
            "candidate_count": len(FAST_SALE_BENCHMARK_CANDIDATE_SPECS),
            "split_kind": "grouped_forward",
            "row_grain": "one row per item observation at as_of_ts with identity-safe split",
            "tail_metric_quantile": 0.9,
            "allowed_columns": list(BENCHMARK_EXTRACT_COLUMNS),
            "forbidden_feature_patterns": list(BENCHMARK_FORBIDDEN_FEATURE_PATTERNS),
            "price_units": ["chaos", "divine"],
        }
    )
    return contract


def _fast_sale_ranking_rows(
    results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ranking = []
    for result in results:
        validation = cast(Mapping[str, Any], result.get("validation") or {})
        test = cast(Mapping[str, Any], result.get("test") or {})
        validation_tail = cast(Mapping[str, Any], validation.get("tail_metrics") or {})
        test_tail = cast(Mapping[str, Any], test.get("tail_metrics") or {})
        ranking.append(
            {
                "candidate": result["candidate"],
                "validation_mdape": validation["mdape"],
                "test_mdape": test["mdape"],
                "validation_tail_mdape": validation_tail.get(
                    "mdape", validation["mdape"]
                ),
                "test_tail_mdape": test_tail.get("mdape", test["mdape"]),
                "validation_wape": validation["wape"],
                "test_wape": test["wape"],
                "validation_tail_wape": validation_tail.get("wape", validation["wape"]),
                "test_tail_wape": test_tail.get("wape", test["wape"]),
                "validation_interval_80_coverage": validation["interval_80_coverage"],
                "test_interval_80_coverage": test["interval_80_coverage"],
            }
        )
    return sorted(
        ranking,
        key=lambda row: (
            row["validation_tail_mdape"],
            row["validation_mdape"],
            row["test_tail_mdape"],
            row["candidate"],
        ),
    )


def run_fast_sale_benchmark(
    rows: Sequence[Mapping[str, Any]],
    *,
    split_kind: str = "grouped_forward",
    candidate_specs: Sequence[CandidateSpec] = FAST_SALE_BENCHMARK_CANDIDATE_SPECS,
) -> dict[str, Any]:
    if split_kind != "grouped_forward":
        raise ValueError(
            f"unsupported split kind {split_kind!r}; only 'grouped_forward' is allowed"
        )
    if len(candidate_specs) != len(FAST_SALE_BENCHMARK_CANDIDATE_SPECS):
        raise ValueError("fast-sale benchmark must contain exactly 3 candidates")
    filtered_rows = _sold_only_rows(rows)
    validate_benchmark_rows(filtered_rows)
    split = split_grouped_forward_benchmark_rows(filtered_rows)
    trained_candidates = [
        _train_candidate(
            spec,
            split,
            tail_quantile=0.9,
            feature_builder=_fast_sale_feature_dict,
        )
        for spec in candidate_specs
    ]
    candidate_results = [_candidate_summary(result) for result in trained_candidates]
    ranking = _fast_sale_ranking_rows(candidate_results)
    best_candidate = ranking[0] if ranking else {}
    identity_sets = {
        name: {
            str(row.get("identity_key") or row.get("item_id") or "")
            for row in split[name]
        }
        for name in ("train", "validation", "test")
    }
    return {
        "benchmark": "fast_sale_24h_price_benchmark_v1",
        "contract": fast_sale_benchmark_contract(),
        "split": {
            "kind": split_kind,
            "train_rows": len(split["train"]),
            "validation_rows": len(split["validation"]),
            "test_rows": len(split["test"]),
            "train_start_as_of_ts": str(split["train"][0].get("as_of_ts") or ""),
            "validation_start_as_of_ts": str(
                split["validation"][0].get("as_of_ts") or ""
            ),
            "test_start_as_of_ts": str(split["test"][0].get("as_of_ts") or ""),
            "train_identity_count": len(identity_sets["train"]),
            "validation_identity_count": len(identity_sets["validation"]),
            "test_identity_count": len(identity_sets["test"]),
            "identity_overlap_count": len(
                (identity_sets["train"] & identity_sets["validation"])
                | (identity_sets["train"] & identity_sets["test"])
                | (identity_sets["validation"] & identity_sets["test"])
            ),
        },
        "row_count": len(filtered_rows),
        "candidate_results": candidate_results,
        "ranking": ranking,
        "best_candidate": best_candidate,
    }


def run_pricing_benchmark(
    rows: Sequence[Mapping[str, Any]],
    *,
    split_kind: str = "forward",
    candidate_specs: Sequence[CandidateSpec] = BENCHMARK_CANDIDATE_SPECS,
) -> dict[str, Any]:
    if split_kind != "forward":
        raise ValueError(
            f"unsupported split kind {split_kind!r}; only 'forward' is allowed"
        )
    validate_benchmark_rows(rows)
    split = split_benchmark_rows(rows)
    trained_candidates = [_train_candidate(spec, split) for spec in candidate_specs]
    candidate_results = [_candidate_summary(result) for result in trained_candidates]
    ranking = sorted(
        (
            {
                "candidate": result["candidate"],
                "validation_mdape": result["validation"]["mdape"],
                "test_mdape": result["test"]["mdape"],
                "validation_wape": result["validation"]["wape"],
                "test_wape": result["test"]["wape"],
                "validation_interval_80_coverage": result["validation"][
                    "interval_80_coverage"
                ],
                "test_interval_80_coverage": result["test"]["interval_80_coverage"],
            }
            for result in candidate_results
        ),
        key=lambda row: (row["validation_mdape"], row["test_mdape"], row["candidate"]),
    )
    best_candidate = ranking[0] if ranking else {}
    return {
        "contract": benchmark_contract(),
        "split": {
            "kind": split_kind,
            "train_rows": len(split["train"]),
            "validation_rows": len(split["validation"]),
            "test_rows": len(split["test"]),
            "train_start_as_of_ts": str(split["train"][0].get("as_of_ts") or ""),
            "validation_start_as_of_ts": str(
                split["validation"][0].get("as_of_ts") or ""
            ),
            "test_start_as_of_ts": str(split["test"][0].get("as_of_ts") or ""),
        },
        "candidate_results": candidate_results,
        "ranking": ranking,
        "best_candidate": best_candidate,
    }


def format_benchmark_report(report: Mapping[str, Any]) -> str:
    lines = ["# ML Pricing Benchmark Report", ""]
    contract = report.get("contract") or {}
    split = report.get("split") or {}
    lines.append(f"- Contract: {contract.get('name', 'unknown')}")
    lines.append(f"- Split: {split.get('kind', 'forward')}")
    if contract.get("price_units"):
        lines.append(
            f"- Price units: {', '.join(str(unit) for unit in contract.get('price_units', []))}"
        )
    lines.append(
        f"- Rows: train={split.get('train_rows', 0)} validation={split.get('validation_rows', 0)} test={split.get('test_rows', 0)}"
    )
    lines.append("")
    lines.append("| Candidate | Val MDAPE | Test MDAPE | Val WAPE | Test WAPE |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in report.get("ranking", []):
        lines.append(
            f"| {row['candidate']} | {row['validation_mdape']:.4f} | {row['test_mdape']:.4f} | {row['validation_wape']:.4f} | {row['test_wape']:.4f} |"
        )
    best = report.get("best_candidate") or {}
    top_single = next(
        (
            row
            for row in report.get("ranking", [])
            if row.get("candidate") != "stacked_ensemble_log"
        ),
        None,
    )
    if best:
        lines.extend(
            [
                "",
                f"Best candidate: {best.get('candidate', 'unknown')} (val MDAPE={best.get('validation_mdape', 0.0):.4f}, test MDAPE={best.get('test_mdape', 0.0):.4f})",
            ]
        )
    if top_single:
        lines.append(
            f"Top single-model: {top_single['candidate']} (val MDAPE={top_single['validation_mdape']:.4f}, test MDAPE={top_single['test_mdape']:.4f})"
        )
    return "\n".join(lines) + "\n"


def _write_report_bundle(
    report: Mapping[str, Any],
    output_path: str | Path,
    *,
    formatter: Callable[[Mapping[str, Any]], str],
    text_output: bool = False,
) -> dict[str, str]:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if text_output:
        path.write_text(formatter(report), encoding="utf-8")
        json_path = path.with_suffix(".json")
        json_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return {"json": str(json_path), "markdown": str(path)}

    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path = path.parent / f"{path.name}.md"
    markdown_path.write_text(formatter(report), encoding="utf-8")
    return {"json": str(path), "markdown": str(markdown_path)}


def write_benchmark_report(
    report: Mapping[str, Any],
    output_path: str | Path,
    *,
    text_output: bool = False,
) -> dict[str, str]:
    return _write_report_bundle(
        report,
        output_path,
        formatter=format_benchmark_report,
        text_output=text_output,
    )


def format_fast_sale_benchmark_report(report: Mapping[str, Any]) -> str:
    lines = ["# Fast-Sale 24h Benchmark Report", ""]
    contract = report.get("contract") or {}
    split = report.get("split") or {}
    lines.append(f"- Contract: {contract.get('name', 'unknown')}")
    lines.append(f"- Split: {split.get('kind', 'grouped_forward')}")
    if contract.get("price_units"):
        lines.append(
            f"- Price units: {', '.join(str(unit) for unit in contract.get('price_units', []))}"
        )
    lines.append(
        f"- Rows: train={split.get('train_rows', 0)} validation={split.get('validation_rows', 0)} test={split.get('test_rows', 0)}"
    )
    lines.append(
        f"- Identity overlap: {split.get('identity_overlap_count', 'unknown')}"
    )
    lines.append("")
    lines.append(
        "| Candidate | Val MDAPE | Test MDAPE | Val Tail MDAPE | Test Tail MDAPE | Val WAPE | Test WAPE |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in report.get("ranking", []):
        lines.append(
            f"| {row['candidate']} | {row['validation_mdape']:.4f} | {row['test_mdape']:.4f} | {row['validation_tail_mdape']:.4f} | {row['test_tail_mdape']:.4f} | {row['validation_wape']:.4f} | {row['test_wape']:.4f} |"
        )
    best = report.get("best_candidate") or {}
    if best:
        lines.extend(
            [
                "",
                f"Best candidate: {best.get('candidate', 'unknown')} (val tail MDAPE={best.get('validation_tail_mdape', 0.0):.4f}, test tail MDAPE={best.get('test_tail_mdape', 0.0):.4f})",
            ]
        )
    return "\n".join(lines) + "\n"


def write_fast_sale_benchmark_report(
    report: Mapping[str, Any],
    output_path: str | Path,
    *,
    text_output: bool = False,
) -> dict[str, str]:
    return _write_report_bundle(
        report,
        output_path,
        formatter=format_fast_sale_benchmark_report,
        text_output=text_output,
    )


def save_fast_sale_benchmark_artifacts(
    report: Mapping[str, Any], output_path: str | Path
) -> dict[str, Any]:
    text_output = Path(output_path).suffix.lower() in {".txt", ".md"}
    artifacts = write_fast_sale_benchmark_report(
        report, output_path, text_output=text_output
    )
    bundle_path = Path(output_path).parent / f"{Path(output_path).name}.joblib"
    joblib.dump(report, bundle_path)
    return {
        **report,
        "artifacts": {
            **artifacts,
            "joblib": str(bundle_path),
        },
    }


def _family_metric_row(
    family: str,
    row: Mapping[str, Any],
    *,
    is_family_winner: bool,
) -> dict[str, Any]:
    return {
        "family": family,
        "candidate": row.get("candidate"),
        "validation_mdape": row.get("validation_mdape"),
        "test_mdape": row.get("test_mdape"),
        "validation_wape": row.get("validation_wape"),
        "test_wape": row.get("test_wape"),
        "validation_interval_80_coverage": row.get("validation_interval_80_coverage"),
        "test_interval_80_coverage": row.get("test_interval_80_coverage"),
        "is_family_winner": is_family_winner,
    }


def build_item_family_benchmark_report(
    family_reports: Mapping[str, Mapping[str, Any]],
    *,
    league: str,
    as_of_ts: str,
    sample_size: int = 10_000,
    families: Sequence[str] = ITEM_FAMILY_NAMES,
) -> dict[str, Any]:
    normalized_families = [str(family).strip().lower() for family in families]
    unknown_families = [
        family for family in normalized_families if family not in ITEM_FAMILY_NAMES
    ]
    if unknown_families:
        raise ValueError(f"unknown item families: {', '.join(unknown_families)}")
    if len(set(normalized_families)) != len(normalized_families):
        raise ValueError("families must not contain duplicates")
    missing_families = [
        family for family in normalized_families if family not in family_reports
    ]
    if missing_families:
        raise ValueError(
            f"missing family benchmark results for: {', '.join(missing_families)}"
        )

    family_report_map: dict[str, dict[str, Any]] = {}
    family_winners: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    for family in normalized_families:
        family_report = dict(family_reports[family])
        family_report.pop("artifacts", None)
        ranking = family_report.get("ranking")
        if not isinstance(ranking, list) or not ranking:
            raise ValueError(
                f"family {family!r} benchmark report must include ranking rows"
            )
        best_candidate = family_report.get("best_candidate")
        if not isinstance(best_candidate, Mapping) or not best_candidate:
            best_candidate = ranking[0]
        family_best_candidate = dict(best_candidate)
        family_report_map[family] = family_report
        family_winners[family] = family_best_candidate
        winner_name = str(family_best_candidate.get("candidate") or "")
        for row in ranking:
            rows.append(
                _family_metric_row(
                    family,
                    row,
                    is_family_winner=str(row.get("candidate") or "") == winner_name,
                )
            )

    return {
        "benchmark": "item_family_pricing_benchmark_v1",
        "contract": benchmark_contract(),
        "league": league,
        "as_of_ts": as_of_ts,
        "sample_size": sample_size,
        "families": normalized_families,
        "row_count": len(rows),
        "family_reports": family_report_map,
        "family_winners": family_winners,
        "rows": rows,
    }


def format_item_family_benchmark_report(report: Mapping[str, Any]) -> str:
    lines = ["# ML Item Family Benchmark Report", ""]
    lines.append(f"- League: {report.get('league', 'unknown')}")
    lines.append(f"- As of: {report.get('as_of_ts', 'unknown')}")
    families = report.get("families", [])
    if isinstance(families, list) and families:
        lines.append(f"- Families: {', '.join(str(family) for family in families)}")
    lines.append(f"- Sample size: {report.get('sample_size', 0)}")
    lines.append(f"- Rows: {report.get('row_count', 0)}")
    lines.append("")
    lines.append(
        "| Family | Candidate | Val MDAPE | Test MDAPE | Val WAPE | Test WAPE | Winner |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for row in report.get("rows", []):
        winner = "★" if row.get("is_family_winner") else ""
        lines.append(
            f"| {row['family']} | {row['candidate']} | {row['validation_mdape']:.4f} | {row['test_mdape']:.4f} | {row['validation_wape']:.4f} | {row['test_wape']:.4f} | {winner} |"
        )
    lines.append("")
    lines.append("Family winners:")
    family_winners = report.get("family_winners", {})
    for family in families:
        winner = (
            family_winners.get(family, {}) if isinstance(family_winners, dict) else {}
        )
        lines.append(
            f"- {family}: {winner.get('candidate', 'unknown')} (val MDAPE={winner.get('validation_mdape', 0.0):.4f}, test MDAPE={winner.get('test_mdape', 0.0):.4f})"
        )
    return "\n".join(lines) + "\n"


def write_item_family_benchmark_report(
    report: Mapping[str, Any],
    output_path: str | Path,
    *,
    text_output: bool = False,
) -> dict[str, str]:
    return _write_report_bundle(
        report,
        output_path,
        formatter=format_item_family_benchmark_report,
        text_output=text_output,
    )


def save_item_family_benchmark_artifacts(
    report: Mapping[str, Any], output_path: str | Path
) -> dict[str, Any]:
    text_output = Path(output_path).suffix.lower() in {".txt", ".md"}
    artifacts = write_item_family_benchmark_report(
        report, output_path, text_output=text_output
    )
    bundle_path = Path(output_path).parent / f"{Path(output_path).name}.joblib"
    joblib.dump(report, bundle_path)
    return {
        **report,
        "artifacts": {
            **artifacts,
            "joblib": str(bundle_path),
        },
    }


def save_benchmark_artifacts(
    rows: Sequence[Mapping[str, Any]], output_path: str | Path
) -> dict[str, Any]:
    report = run_pricing_benchmark(rows)
    text_output = Path(output_path).suffix.lower() in {".txt", ".md"}
    artifacts = write_benchmark_report(report, output_path, text_output=text_output)
    bundle_path = Path(output_path).parent / f"{Path(output_path).name}.joblib"
    joblib.dump(report, bundle_path)
    return {
        **report,
        "artifacts": {
            **artifacts,
            "joblib": str(bundle_path),
        },
    }


def run_mirage_iron_ring_branch_benchmark(
    rows: Sequence[Mapping[str, Any]],
    *,
    candidate_specs: Sequence[CandidateSpec] = BENCHMARK_CANDIDATE_SPECS,
) -> dict[str, Any]:
    validate_benchmark_rows(rows)
    split = split_grouped_forward_benchmark_rows_by_field(
        rows, group_field="normalized_affix_hash"
    )
    trained_candidates = [
        _train_candidate(spec, split, feature_builder=_mirage_feature_dict)
        for spec in candidate_specs
    ]
    candidate_results = [_candidate_summary(result) for result in trained_candidates]
    ranking = sorted(
        (
            {
                "candidate": result["candidate"],
                "validation_mdape": result["validation"]["mdape"],
                "test_mdape": result["test"]["mdape"],
                "validation_wape": result["validation"]["wape"],
                "test_wape": result["test"]["wape"],
                "validation_interval_80_coverage": result["validation"][
                    "interval_80_coverage"
                ],
                "test_interval_80_coverage": result["test"]["interval_80_coverage"],
            }
            for result in candidate_results
        ),
        key=lambda row: (row["validation_mdape"], row["test_mdape"], row["candidate"]),
    )
    best_candidate = ranking[0] if ranking else {}
    contract = benchmark_contract()
    contract["split_kind"] = "grouped_forward"
    return {
        "contract": contract,
        "split": {
            "kind": "grouped_forward",
            "train_rows": len(split["train"]),
            "validation_rows": len(split["validation"]),
            "test_rows": len(split["test"]),
            "train_start_as_of_ts": str(split["train"][0].get("as_of_ts") or ""),
            "validation_start_as_of_ts": str(
                split["validation"][0].get("as_of_ts") or ""
            ),
            "test_start_as_of_ts": str(split["test"][0].get("as_of_ts") or ""),
            "train_identity_count": len(
                {
                    str(row.get("identity_key") or row.get("item_id") or "")
                    for row in split["train"]
                }
            ),
            "validation_identity_count": len(
                {
                    str(row.get("identity_key") or row.get("item_id") or "")
                    for row in split["validation"]
                }
            ),
            "test_identity_count": len(
                {
                    str(row.get("identity_key") or row.get("item_id") or "")
                    for row in split["test"]
                }
            ),
        },
        "candidate_results": candidate_results,
        "ranking": ranking,
        "best_candidate": best_candidate,
    }


def save_mirage_iron_ring_branch_benchmark_artifacts(
    report: Mapping[str, Any], output_path: str | Path
) -> dict[str, Any]:
    text_output = Path(output_path).suffix.lower() in {".txt", ".md"}
    artifacts = write_benchmark_report(report, output_path, text_output=text_output)
    bundle_path = Path(output_path).parent / f"{Path(output_path).name}.joblib"
    joblib.dump(report, bundle_path)
    return {
        **report,
        "artifacts": {
            **artifacts,
            "joblib": str(bundle_path),
        },
    }


def run_lgbm_neo_benchmark(
    rows: pd.DataFrame,
    *,
    min_rows: int = 10_000,
) -> dict[str, Any]:
    if len(rows) < min_rows:
        raise ValueError(
            f"lgbm-neo benchmark requires at least {min_rows} rows; got {len(rows)}"
        )

    frame = _lgbm_neo_feature_frame(rows)
    X_train, X_valid, X_test, y_train, y_valid, y_test, split_meta = (
        _lgbm_neo_split_frame(frame)
    )
    X_train, X_valid, X_test, categorical_columns = _lgbm_neo_prepare_features(
        X_train, X_valid, X_test
    )

    if LGBMRegressor is None:
        model: Any = HistGradientBoostingRegressor(
            learning_rate=0.03,
            max_depth=8,
            max_iter=300,
            random_state=42,
        )
        X_train_fit, X_valid_fit, X_test_fit = (
            _encode_lgbm_neo_categorical_features_for_fallback(
                X_train.copy(), X_valid.copy(), X_test.copy(), categorical_columns
            )
        )
        model.fit(X_train_fit, y_train)
        pred_log_valid = np.asarray(model.predict(X_valid_fit), dtype=float)
        pred_log_test = np.asarray(model.predict(X_test_fit), dtype=float)
    else:
        model = LGBMRegressor(
            objective="regression_l1",
            n_estimators=3000,
            learning_rate=0.03,
            num_leaves=31,
            max_depth=8,
            min_child_samples=10,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_alpha=1.0,
            reg_lambda=2.0,
            use_missing=True,
            zero_as_missing=False,
            feature_pre_filter=False,
            force_col_wise=True,
            random_state=42,
            n_jobs=4,
            verbosity=-1,
        )
        callbacks = []
        if lgb is not None:
            callbacks = [lgb.early_stopping(100), lgb.log_evaluation(50)]
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_valid, y_valid)],
            eval_metric="l1",
            categorical_feature=categorical_columns,
            callbacks=callbacks,
        )
        pred_log_valid = np.asarray(model.predict(X_valid), dtype=float)
        pred_log_test = np.asarray(model.predict(X_test), dtype=float)

    def _price_metrics(y_values: pd.Series, pred_log: np.ndarray) -> dict[str, Any]:
        actual_price = np.asarray(np.expm1(y_values), dtype=float)
        predicted_price = np.asarray(np.expm1(pred_log), dtype=float)
        abs_pct_error = np.abs(predicted_price - actual_price) / np.maximum(
            actual_price, 0.01
        )
        abs_error = np.abs(predicted_price - actual_price)
        log_error = np.square(np.log1p(predicted_price) - np.log1p(actual_price))
        return {
            "sample_count": int(len(y_values)),
            "mdape": float(_median([float(value) for value in abs_pct_error])),
            "wape": float(abs_error.sum() / max(float(actual_price.sum()), 0.01)),
            "rmsle": float(math.sqrt(float(log_error.mean()))),
            "predicted_prices": predicted_price.tolist(),
        }

    validation_metrics = _price_metrics(y_valid, pred_log_valid)
    test_metrics = _price_metrics(y_test, pred_log_test)

    return {
        "benchmark": "lgbm_neo_benchmark_v1",
        "benchmark_number": 11,
        "row_count": int(len(frame)),
        "split": split_meta,
        "contract": {
            "name": "lgbm_neo_benchmark_v1",
            "row_grain": "one row per item observation at observed_at",
            "split_kind": split_meta["kind"],
            "min_rows": min_rows,
            "categorical_columns": categorical_columns,
            "feature_prefixes": ["has_", "val_"],
            "dropped_feature_prefixes": ["tier_"],
        },
        "model": {
            "name": "LGBM-neo",
            "objective": "regression_l1",
            "categorical_columns": categorical_columns,
            "zero_as_missing": False,
            "feature_pre_filter": False,
            "min_child_samples": 10,
            "num_leaves": 31,
            "max_depth": 8,
            "force_col_wise": True,
            "n_jobs": 4,
        },
        "metrics": validation_metrics,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "best_candidate": {
            "candidate": "LGBM-neo",
            "validation_mdape": validation_metrics["mdape"],
            "validation_wape": validation_metrics["wape"],
        },
    }


def format_lgbm_neo_benchmark_report(report: Mapping[str, Any]) -> str:
    lines = ["# LGBM-neo Benchmark Report", ""]
    lines.append(f"- Benchmark #: {report.get('benchmark_number', 11)}")
    lines.append(f"- Rows: {report.get('row_count', 0)}")
    split = report.get("split") or {}
    lines.append(
        f"- Split: train={split.get('train_rows', 0)} validation={split.get('validation_rows', 0)} test={split.get('test_rows', 0)}"
    )
    lines.append(
        f"- Split window: train={split.get('train_observed_at_start', '')}..{split.get('train_observed_at_end', '')} validation={split.get('validation_observed_at_start', '')}..{split.get('validation_observed_at_end', '')} test={split.get('test_observed_at_start', '')}..{split.get('test_observed_at_end', '')}"
    )
    validation_metrics = report.get("validation_metrics") or report.get("metrics") or {}
    test_metrics = report.get("test_metrics") or {}
    lines.append(f"- Validation MDAPE: {validation_metrics.get('mdape', 0.0):.4f}")
    lines.append(f"- Validation WAPE: {validation_metrics.get('wape', 0.0):.4f}")
    lines.append(f"- Test MDAPE: {test_metrics.get('mdape', 0.0):.4f}")
    lines.append(f"- Test WAPE: {test_metrics.get('wape', 0.0):.4f}")
    lines.append("")
    lines.append(
        "| Model | Validation MDAPE | Validation WAPE | Test MDAPE | Test WAPE |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    lines.append(
        f"| {report.get('model', {}).get('name', 'LGBM-neo')} | {validation_metrics.get('mdape', 0.0):.4f} | {validation_metrics.get('wape', 0.0):.4f} | {test_metrics.get('mdape', 0.0):.4f} | {test_metrics.get('wape', 0.0):.4f} |"
    )
    return "\n".join(lines) + "\n"


def save_lgbm_neo_benchmark_artifacts(
    report: Mapping[str, Any], output_path: str | Path
) -> dict[str, Any]:
    text_output = Path(output_path).suffix.lower() in {".txt", ".md"}
    artifacts = _write_report_bundle(
        report,
        output_path,
        formatter=format_lgbm_neo_benchmark_report,
        text_output=text_output,
    )
    bundle_path = Path(output_path).parent / f"{Path(output_path).name}.joblib"
    joblib.dump(report, bundle_path)
    return {
        **report,
        "artifacts": {
            **artifacts,
            "joblib": str(bundle_path),
        },
    }
