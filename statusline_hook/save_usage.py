#!/usr/bin/env python3
"""
Claude Hourglass — statusLine receiver.

Claude Code の statusLine として登録するスクリプト。
Claude Code はターン毎にこのスクリプトを呼び出し、現在のセッション情報を
stdin に JSON として渡す。

フロー:
  stdin (JSON) → SQLite スナップショット保存 + latest_usage.json 更新
  stdout → Claude Code のステータスバーに表示されるテキスト

設定 (.claude/settings.json):
    { "statusLine": "python /path/to/statusline_hook/save_usage.py" }

手動テスト (stdin から JSON を渡す):
    echo '{"captured_at":"...","rate_limits":{...}}' | python save_usage.py

CLI 引数でも可:
    python save_usage.py '{"captured_at":"...","rate_limits":{...}}'

stdin JSON の期待フォーマット (すべてのフィールドは省略可):
{
  "captured_at": "2026-06-25T12:34:56Z",
  "session_id": "abc123",
  "model": { "display_name": "Claude Sonnet 4.6" },
  "rate_limits": {
    "five_hour": { "used_percentage": 42.5, "resets_at": "2026-06-25T17:00:00Z" },
    "seven_day": { "used_percentage": 18.0, "resets_at": "2026-07-01T00:00:00Z" }
  },
  "cost": { "total_cost_usd": 0.1234 },
  "context_window": { "current_usage": 45000 },
  "version": "1.0.0"
}

stdout 出力例 (Claude Code ステータスバーに表示):
  [Hourglass] 5h 42.5% | 7d 18.0%
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate project root and config
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from claude_hourglass import config, database
    from claude_hourglass.models import UsageSnapshot
    _HAS_APP = True
except ImportError:
    _HAS_APP = False


_DEFAULT_DIR = Path.home() / ".claude_hourglass"
_DEFAULT_DB = _DEFAULT_DIR / "usage.sqlite"
_DEFAULT_JSON = _DEFAULT_DIR / "latest_usage.json"


# ---------------------------------------------------------------------------
# Config resolution (without full app config module)
# ---------------------------------------------------------------------------

def _resolve_paths() -> tuple[Path, Path]:
    if _HAS_APP:
        config.load()
        return config.db_path(), config.latest_json_path()

    cfg_file = _DEFAULT_DIR / "config.json"
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            return Path(cfg.get("db_path", _DEFAULT_DB)), Path(cfg.get("latest_json_path", _DEFAULT_JSON))
        except Exception:
            pass
    return _DEFAULT_DB, _DEFAULT_JSON


# ---------------------------------------------------------------------------
# Standalone DB / JSON helpers (used when app module not available)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at             TEXT NOT NULL,
    session_id              TEXT,
    model_display_name      TEXT,
    five_hour_used_pct      REAL,
    five_hour_resets_at     TEXT,
    seven_day_used_pct      REAL,
    seven_day_resets_at     TEXT,
    total_cost_usd          REAL,
    context_window_current  INTEGER,
    version                 TEXT,
    raw_json                TEXT,
    created_at              TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_captured_at ON usage_snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_session_id  ON usage_snapshots(session_id);
"""


def _ts_to_iso(val) -> Optional[str]:
    """エポック秒 (int/float) または文字列を ISO UTC 文字列に変換する。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None
    return str(val)


def _save_standalone(data: dict, db_path: Path, json_path: Path) -> None:
    import sqlite3

    db_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    rate = data.get("rate_limits", {})
    five_hour = rate.get("five_hour", {})
    seven_day = rate.get("seven_day", {})
    cost = data.get("cost", {})
    ctx = data.get("context_window", {})
    model = data.get("model", {})

    row = (
        _ts_to_iso(data.get("captured_at")) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        data.get("session_id"),
        model.get("display_name"),
        five_hour.get("used_percentage"),
        _ts_to_iso(five_hour.get("resets_at")),
        seven_day.get("used_percentage"),
        _ts_to_iso(seven_day.get("resets_at")),
        cost.get("total_cost_usd"),
        ctx.get("current_usage"),
        data.get("version"),
        json.dumps(data, ensure_ascii=False),
    )

    con = sqlite3.connect(str(db_path))
    con.executescript(_SCHEMA)
    con.execute(
        """INSERT INTO usage_snapshots
           (captured_at, session_id, model_display_name,
            five_hour_used_pct, five_hour_resets_at,
            seven_day_used_pct, seven_day_resets_at,
            total_cost_usd, context_window_current, version, raw_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        row,
    )
    con.commit()
    con.close()

    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Read JSON from CLI arg or stdin
    raw: str = ""
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    else:
        raw = sys.stdin.read()

    raw = raw.strip()
    if not raw:
        print("save_usage.py: no input received", file=sys.stderr)
        return 1

    try:
        data: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"save_usage.py: invalid JSON — {exc}", file=sys.stderr)
        return 1

    # Ensure captured_at
    if "captured_at" not in data:
        data["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    db_path, json_path = _resolve_paths()

    try:
        if _HAS_APP:
            database.init(db_path)
            snap = UsageSnapshot.from_status_json(data)
            database.insert(db_path, snap)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            _save_standalone(data, db_path, json_path)
    except Exception as exc:
        print(f"save_usage.py: failed to save — {exc}", file=sys.stderr)
        return 1

    h5 = data.get("rate_limits", {}).get("five_hour", {}).get("used_percentage", 0)
    h7 = data.get("rate_limits", {}).get("seven_day", {}).get("used_percentage", 0)
    print(f"[Hourglass] 5h {h5:.1f}% | 7d {h7:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
