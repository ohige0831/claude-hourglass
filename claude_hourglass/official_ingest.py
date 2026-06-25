"""
official_ingest.py — 公式UI使用データの共有インジェスト関数。

呼び出し元:
  - receiver.py (Tampermonkey HTTP POST)
  - official_webview_collector.py (QtWebEngine)
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from .sources import SOURCE_LABELS, build_latest_json


def ingest_official_usage(
    data: dict,
    official_ui_path: Path,
    statusline_raw_path: Path,
    latest_path: Path,
    alt_max_age_secs: int = 600,
    source_detail: str = "",
) -> None:
    """公式UIデータを保存して latest_usage.json を再構築する。"""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["source"] = "official_ui"
    data["source_label"] = SOURCE_LABELS.get("official_ui", "Official UI")
    if source_detail:
        data["source_detail"] = source_detail
    data["saved_at"] = now_iso
    data.setdefault("captured_at", now_iso)

    official_ui_path.parent.mkdir(parents=True, exist_ok=True)
    official_ui_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    build_latest_json(
        statusline_raw_path, official_ui_path, latest_path,
        alt_max_age_secs=alt_max_age_secs,
    )
