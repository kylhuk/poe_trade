from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..etl.models import CurrencySnapshot


@dataclass
class ChaosScaleEngine:
    base_rates: Mapping[str, float]

    @classmethod
    def from_snapshots(cls, snapshots: Iterable[CurrencySnapshot]) -> "ChaosScaleEngine":
        rates = {snapshot.currency.lower(): snapshot.chaos_value for snapshot in snapshots}
        return cls(base_rates=rates)

    def normalize_price(self, price: float, currency: str) -> float:
        return price * self.base_rates.get(currency.lower(), 1.0)

    def normalize_listing(self, price: float, currency: str) -> float:
        return self.normalize_price(price, currency)
