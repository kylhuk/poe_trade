from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    realm: str
    league: str
    start_snapshot: str
    end_snapshot: str
    start_value: float
    end_value: float
    start_time: datetime
    end_time: datetime
    tag: Optional[str] = None
    notes: Optional[str] = None


def _duration_seconds(snapshot: SessionSnapshot) -> float:
    return max((snapshot.end_time - snapshot.start_time).total_seconds(), 1.0)


@dataclass(frozen=True)
class FarmingSessionRow:
    session_id: str
    realm: str
    league: str
    start_snapshot: str
    end_snapshot: str
    tag: Optional[str]
    duration_s: float
    profit_chaos: float
    profit_per_hour: float
    notes: Optional[str]

    def to_row(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "realm": self.realm,
            "league": self.league,
            "start_snapshot": self.start_snapshot,
            "end_snapshot": self.end_snapshot,
            "tag": self.tag,
            "duration_s": self.duration_s,
            "profit_chaos": self.profit_chaos,
            "profit_per_hour": self.profit_per_hour,
            "notes": self.notes,
        }


def summarize_session(snapshot: SessionSnapshot) -> FarmingSessionRow:
    duration = _duration_seconds(snapshot)
    profit = snapshot.end_value - snapshot.start_value
    profit_per_hour = profit / (duration / 3600)
    return FarmingSessionRow(
        session_id=snapshot.session_id,
        realm=snapshot.realm,
        league=snapshot.league,
        start_snapshot=snapshot.start_snapshot,
        end_snapshot=snapshot.end_snapshot,
        tag=snapshot.tag,
        duration_s=duration,
        profit_chaos=profit,
        profit_per_hour=profit_per_hour,
        notes=snapshot.notes,
    )


def compute_session_profit(snapshot: SessionSnapshot) -> FarmingSessionRow:
    return summarize_session(snapshot)

