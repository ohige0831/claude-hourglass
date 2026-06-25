"""
sources.py — マルチソース優先度マージ。

latest_usage.json を複数ソースの最新データから組み立てる。

優先度:
  official_ui (5分以内) > statusline best-state > stale official_ui

呼び出し元:
  - statusline_hook/save_usage.py (statusLine ターン毎)
  - receiver.py (HTTP POST 受信時)
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ASCII labels written into JSON files (source_label field)
SOURCE_LABELS: dict[str, str] = {
    "official_ui": "Official UI",
    "statusline": "statusLine",
    "manual": "Manual",
    "seed": "Seed",
    "unknown": "Unknown",
}

# Japanese labels used only in Qt UI — never written to JSON
SOURCE_LABELS_JA: dict[str, str] = {
    "official_ui": "公式UI",
    "statusline": "statusLine",
    "manual": "手動",
    "seed": "シード",
    "unknown": "不明",
}

OFFICIAL_UI_MAX_AGE_SECS = 300  # 5 minutes

# これらのソースは比較 alt として表示しない (手動テスト / シードデータ)
_ALT_SKIP_SOURCES: frozenset[str] = frozenset({"manual", "seed"})


def _parse_ts(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc)
        except Exception:
            return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(val), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _is_fresh(data: dict, max_age_secs: int) -> bool:
    """saved_at または captured_at が max_age_secs 以内なら True。"""
    for key in ("saved_at", "captured_at"):
        dt = _parse_ts(data.get(key))
        if dt is not None:
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            return age <= max_age_secs
    return False


def _is_alt_valid(data: dict, max_age_secs: int) -> bool:
    """alt source として比較表示に使えるかを判定する。"""
    if data.get("source") in _ALT_SKIP_SOURCES:
        return False
    return _is_fresh(data, max_age_secs)


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_latest_json(
    statusline_raw_path: Path,
    official_ui_path: Path,
    output_path: Path,
    alt_max_age_secs: int = 600,
) -> dict:
    """
    statusline_raw と official_ui を優先度に従って選択し、
    latest_usage.json を書き出す。戻り値: 書き込んだ dict。
    """
    statusline_data = _load_json(statusline_raw_path)
    official_ui_data = _load_json(official_ui_path)

    official_fresh = (
        official_ui_data is not None
        and _is_fresh(official_ui_data, OFFICIAL_UI_MAX_AGE_SECS)
    )

    if official_fresh:
        primary = dict(official_ui_data)
        primary["source"] = "official_ui"
        alt = statusline_data
        alt_source = "statusline"
    elif statusline_data is not None:
        primary = dict(statusline_data)
        primary["source"] = "statusline"
        alt = official_ui_data
        alt_source = "official_ui"
    elif official_ui_data is not None:
        primary = dict(official_ui_data)
        primary["source"] = "official_ui"
        alt = None
        alt_source = None
    else:
        return {}

    primary["source_label"] = SOURCE_LABELS.get(primary["source"], primary["source"])

    # Alt source metadata — only when alt is fresh enough and not a skip-source type
    if alt and alt.get("rate_limits") and _is_alt_valid(alt, alt_max_age_secs):
        alt_rate = alt["rate_limits"]
        alt_5h = alt_rate.get("five_hour") or {}
        alt_7d = alt_rate.get("seven_day") or {}
        primary["alt_source"] = alt_source
        primary["alt_source_label"] = SOURCE_LABELS.get(alt_source or "", alt_source or "")
        primary["alt_five_hour_pct"] = alt_5h.get("used_percentage")
        primary["alt_seven_day_pct"] = alt_7d.get("used_percentage")
        primary["alt_rate_limits"] = alt_rate
        primary["alt_captured_at"] = alt.get("captured_at")
    else:
        for key in ("alt_source", "alt_source_label", "alt_five_hour_pct",
                    "alt_seven_day_pct", "alt_rate_limits", "alt_captured_at"):
            primary.pop(key, None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(primary, indent=2, ensure_ascii=False), encoding="utf-8")
    return primary
