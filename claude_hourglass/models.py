from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import json


def _normalize_ts(val) -> Optional[str]:
    """Unix epoch int/float → ISO UTC string; str は通過; None はそのまま。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None
    return str(val)


@dataclass
class UsageSnapshot:
    captured_at: str
    session_id: Optional[str] = None
    model_display_name: Optional[str] = None
    five_hour_used_pct: Optional[float] = None
    five_hour_resets_at: Optional[str] = None
    seven_day_used_pct: Optional[float] = None
    seven_day_resets_at: Optional[str] = None
    total_cost_usd: Optional[float] = None
    context_window_current: Optional[int] = None
    version: Optional[str] = None
    raw_json: Optional[str] = None
    id: Optional[int] = field(default=None, compare=False)

    @classmethod
    def from_status_json(cls, data: dict) -> "UsageSnapshot":
        rate = data.get("rate_limits", {})
        five_hour = rate.get("five_hour", {})
        seven_day = rate.get("seven_day", {})
        cost = data.get("cost", {})
        ctx = data.get("context_window", {})
        model = data.get("model", {})

        return cls(
            captured_at=_normalize_ts(data.get("captured_at")) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            session_id=data.get("session_id"),
            model_display_name=model.get("display_name"),
            five_hour_used_pct=five_hour.get("used_percentage"),
            five_hour_resets_at=_normalize_ts(five_hour.get("resets_at")),
            seven_day_used_pct=seven_day.get("used_percentage"),
            seven_day_resets_at=_normalize_ts(seven_day.get("resets_at")),
            total_cost_usd=cost.get("total_cost_usd"),
            context_window_current=ctx.get("current_usage"),
            version=data.get("version"),
            raw_json=json.dumps(data, ensure_ascii=False),
        )

    def to_dict(self) -> dict:
        return {
            "captured_at": self.captured_at,
            "session_id": self.session_id,
            "model_display_name": self.model_display_name,
            "five_hour_used_pct": self.five_hour_used_pct,
            "five_hour_resets_at": self.five_hour_resets_at,
            "seven_day_used_pct": self.seven_day_used_pct,
            "seven_day_resets_at": self.seven_day_resets_at,
            "total_cost_usd": self.total_cost_usd,
            "context_window_current": self.context_window_current,
            "version": self.version,
        }
