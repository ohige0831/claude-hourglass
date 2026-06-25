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


def _to_int(val) -> Optional[int]:
    """スカラー値を int に変換する。dict/list などは None を返す。"""
    if val is None:
        return None
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(float(val))
        except Exception:
            return None
    return None  # dict / list → 変換不可


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
    # multi-source fields
    source: Optional[str] = None
    source_label: Optional[str] = None
    alt_source: Optional[str] = None
    alt_source_label: Optional[str] = None
    alt_five_hour_pct: Optional[float] = None
    alt_seven_day_pct: Optional[float] = None

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
            context_window_current=_to_int(ctx.get("current_usage")),
            version=data.get("version"),
            raw_json=json.dumps(data, ensure_ascii=False),
            source=data.get("source"),
            source_label=data.get("source_label"),
            alt_source=data.get("alt_source"),
            alt_source_label=data.get("alt_source_label"),
            alt_five_hour_pct=data.get("alt_five_hour_pct"),
            alt_seven_day_pct=data.get("alt_seven_day_pct"),
        )

    # ------------------------------------------------------------------
    # Expiry-aware effective values (UI 表示用)
    # ------------------------------------------------------------------

    @staticmethod
    def _resets_at_expired(resets_at: Optional[str]) -> bool:
        """resets_at が現在時刻以前なら True（枠がリセット済み）。"""
        if not resets_at:
            return False
        try:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(resets_at, fmt).replace(tzinfo=timezone.utc)
                    return dt <= datetime.now(timezone.utc)
                except ValueError:
                    pass
        except Exception:
            pass
        return False

    @property
    def five_hour_expired(self) -> bool:
        return self._resets_at_expired(self.five_hour_resets_at)

    @property
    def seven_day_expired(self) -> bool:
        return self._resets_at_expired(self.seven_day_resets_at)

    @property
    def effective_five_hour_pct(self) -> float:
        """リセット済みなら 0.0、そうでなければ raw 値。"""
        return 0.0 if self.five_hour_expired else (self.five_hour_used_pct or 0.0)

    @property
    def effective_seven_day_pct(self) -> float:
        return 0.0 if self.seven_day_expired else (self.seven_day_used_pct or 0.0)

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
