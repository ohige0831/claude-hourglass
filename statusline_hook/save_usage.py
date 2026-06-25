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

try:
    from claude_hourglass import sources as _sources_mod
    _HAS_SOURCES = True
except ImportError:
    _HAS_SOURCES = False


_DEFAULT_DIR = Path.home() / ".claude_hourglass"
_DEFAULT_DB = _DEFAULT_DIR / "usage.sqlite"
_DEFAULT_JSON = _DEFAULT_DIR / "latest_usage.json"
_DEFAULT_STATUSLINE_RAW = _DEFAULT_DIR / "latest_statusline_raw.json"
_DEFAULT_OFFICIAL_UI = _DEFAULT_DIR / "latest_official_ui.json"


# ---------------------------------------------------------------------------
# Config resolution (without full app config module)
# ---------------------------------------------------------------------------

def _resolve_paths() -> tuple[Path, Path, Path, Path]:
    """(db_path, latest_json, statusline_raw, official_ui) を返す。"""
    if _HAS_APP:
        config.load()
        return (
            config.db_path(),
            config.latest_json_path(),
            config.statusline_raw_path(),
            config.official_ui_path(),
        )

    cfg_file = _DEFAULT_DIR / "config.json"
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            return (
                Path(cfg.get("db_path", _DEFAULT_DB)),
                Path(cfg.get("latest_json_path", _DEFAULT_JSON)),
                Path(cfg.get("latest_statusline_raw_path", _DEFAULT_STATUSLINE_RAW)),
                Path(cfg.get("latest_official_ui_path", _DEFAULT_OFFICIAL_UI)),
            )
        except Exception:
            pass
    return _DEFAULT_DB, _DEFAULT_JSON, _DEFAULT_STATUSLINE_RAW, _DEFAULT_OFFICIAL_UI


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


def _ts_to_iso(val) -> "str | None":
    """エポック秒 (int/float) または文字列を ISO UTC 文字列に変換する。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None
    return str(val)


def _sql_safe(val) -> "int | float | str | bytes | None":
    """SQLite が受け付けない型 (dict/list 等) を TEXT に変換する。"""
    if val is None or isinstance(val, (int, float, str, bytes)):
        return val
    if isinstance(val, bool):
        return int(val)
    try:
        return json.dumps(val, ensure_ascii=False)
    except Exception:
        return str(val)


def _save_db_only(data: dict, db_path: Path) -> None:
    """SQLite にのみ保存する (app module が使えない場合のフォールバック)。"""
    import sqlite3

    db_path.parent.mkdir(parents=True, exist_ok=True)

    rate = data.get("rate_limits", {})
    five_hour = rate.get("five_hour", {})
    seven_day = rate.get("seven_day", {})
    cost = data.get("cost", {})
    ctx = data.get("context_window", {})
    model = data.get("model", {})

    raw_values = (
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
    row = tuple(_sql_safe(v) for v in raw_values)

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


# ---------------------------------------------------------------------------
# Rate-limit generation merge
# ---------------------------------------------------------------------------

def _parse_resets_dt(val) -> "datetime | None":
    """resets_at の int/float/str を UTC datetime に変換する。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc)
        except Exception:
            return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(val), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _merge_one_limit(
    key: str,
    existing: dict,
    incoming: dict,
    in_session: "str | None",
    ex_session: "str | None",
    now: datetime,
    notes: list,
) -> dict:
    """1つの rate limit エントリのマージ。採用するデータを返す。"""
    ex_dt = _parse_resets_dt(existing.get("resets_at"))
    in_dt = _parse_resets_dt(incoming.get("resets_at"))
    ex_pct = float(existing.get("used_percentage") or 0.0)
    in_pct = float(incoming.get("used_percentage") or 0.0)

    # existing がない → incoming を無条件採用
    if ex_dt is None:
        return incoming

    # incoming に resets_at がない → そのまま採用
    if in_dt is None:
        return incoming

    # stale incoming: resets_at が過去かつ used_pct > 0 → 巻き戻り防止
    if in_dt <= now and in_pct > 0:
        if ex_dt > now:
            notes.append(f"{key}:stale-ignored(in={in_pct:.0f}%,ex_resets=future)")
            return existing
        # 両方 expired → incoming を採用（更新待ち状態）
        notes.append(f"{key}:both-expired")
        return incoming

    # 新しい世代 (resets_at が進んだ) → 採用
    if in_dt > ex_dt:
        notes.append(f"{key}:new-window({ex_pct:.0f}%→{in_pct:.0f}%)")
        return incoming

    # 同じ世代
    if in_dt == ex_dt:
        if in_pct >= ex_pct:
            return incoming  # 上昇 or 同値 → 常に採用
        # 使用率が下がるケース
        if in_session and in_session == ex_session:
            notes.append(f"{key}:same-session-decrease({ex_pct:.0f}%→{in_pct:.0f}%)")
            return incoming  # 同一セッション → 採用
        notes.append(f"{key}:cross-session-decrease-ignored({ex_pct:.0f}%→{in_pct:.0f}%)")
        return existing  # 別セッションの逆行 → 保持

    # 古い世代 → 既存を保持
    notes.append(f"{key}:old-window-ignored")
    return existing


def _merge_latest_json(existing: dict, incoming: dict, notes: list) -> dict:
    """rate limits の世代管理マージ。その他フィールド (cost/model 等) は incoming 優先。"""
    result = dict(incoming)

    ex_rate = existing.get("rate_limits") or {}
    in_rate = incoming.get("rate_limits") or {}

    if not in_rate:
        return result

    now = datetime.now(timezone.utc)
    in_session = incoming.get("session_id")
    ex_session = existing.get("session_id")

    merged_rate = dict(in_rate)
    for key in ("five_hour", "seven_day"):
        ex_limit = ex_rate.get(key) or {}
        in_limit = in_rate.get(key) or {}
        merged_rate[key] = _merge_one_limit(
            key=key,
            existing=ex_limit,
            incoming=in_limit,
            in_session=in_session,
            ex_session=ex_session,
            now=now,
            notes=notes,
        )

    result["rate_limits"] = merged_rate
    return result


# ---------------------------------------------------------------------------
# Debug log
# ---------------------------------------------------------------------------

_DEBUG_LOG = _DEFAULT_DIR / "statusline_debug.log"


def _write_debug(
    data: dict,
    *,
    db_saved: bool = False,
    db_err: str = "",
    raw_saved: bool = False,
    raw_err: str = "",
    latest_saved: bool = False,
    json_err: str = "",
    latest_path: "Path | None" = None,
    merge_notes: "list | None" = None,
    source: str = "statusline",
) -> None:
    try:
        rate = data.get("rate_limits", {})
        fh = rate.get("five_hour", {})
        sd = rate.get("seven_day", {})
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts = [
            now, "called",
            f"session={data.get('session_id', '—')}",
            f"has_rate_limits={str(bool(rate)).lower()}",
            f"5h={fh.get('used_percentage', '—')}",
            f"7d={sd.get('used_percentage', '—')}",
            f"captured_at={data.get('captured_at', '—')}",
            f"source={source}",
            f"raw_saved={str(raw_saved).lower()}",
            f"latest_saved={str(latest_saved).lower()}",
            f"latest_path={latest_path or _DEFAULT_JSON}",
            f"db_saved={str(db_saved).lower()}",
        ]
        if merge_notes:
            parts.append(f"merge=[{','.join(merge_notes)}]")
        if db_err:
            parts.append(f"db_error={db_err!r}")
        if raw_err:
            parts.append(f"raw_error={raw_err!r}")
        if json_err:
            parts.append(f"json_error={json_err!r}")
        _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(" ".join(parts) + "\n")
    except Exception:
        pass


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

    db_path, json_path, raw_path, official_ui_path = _resolve_paths()

    # ---- DB 保存 (失敗しても続行) ----
    db_saved = False
    db_err = ""
    try:
        if _HAS_APP:
            database.init(db_path)
            snap = UsageSnapshot.from_status_json(data)
            database.insert(db_path, snap)
        else:
            _save_db_only(data, db_path)
        db_saved = True
    except Exception as exc:
        db_err = str(exc)
        print(f"save_usage.py: DB save failed — {exc}", file=sys.stderr)

    # ---- latest_statusline_raw.json 保存 (世代管理マージ) ----
    raw_saved = False
    raw_err = ""
    merge_notes: list = []
    merged_raw: dict = data
    try:
        raw_path.parent.mkdir(parents=True, exist_ok=True)

        existing_raw: dict = {}
        if raw_path.exists():
            try:
                existing_raw = json.loads(raw_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        merged_raw = _merge_latest_json(existing_raw, data, merge_notes)
        merged_raw["source"] = "statusline"
        merged_raw["source_label"] = _sources_mod.SOURCE_LABELS.get("statusline", "statusLine") if _HAS_SOURCES else "statusLine"
        raw_path.write_text(json.dumps(merged_raw, indent=2, ensure_ascii=False), encoding="utf-8")
        raw_saved = True
    except Exception as exc:
        raw_err = str(exc)
        print(f"save_usage.py: raw JSON save failed — {exc}", file=sys.stderr)

    # ---- latest_usage.json 更新 (sources 優先度マージ) ----
    latest_saved = False
    json_err = ""
    merged_data: dict = merged_raw
    alt_max_age = (config.get("alt_max_age_secs") or 600) if _HAS_APP else 600
    try:
        if _HAS_SOURCES:
            result = _sources_mod.build_latest_json(
                raw_path, official_ui_path, json_path,
                alt_max_age_secs=alt_max_age,
            )
            if result:
                merged_data = result
        else:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(merged_raw, indent=2, ensure_ascii=False), encoding="utf-8")
        latest_saved = True
    except Exception as exc:
        json_err = str(exc)
        print(f"save_usage.py: latest JSON update failed — {exc}", file=sys.stderr)

    _write_debug(
        data,
        db_saved=db_saved, db_err=db_err,
        raw_saved=raw_saved, raw_err=raw_err,
        latest_saved=latest_saved, json_err=json_err,
        latest_path=json_path,
        merge_notes=merge_notes,
        source="statusline",
    )

    # stdout: merged の実効値を表示
    merged_rate = merged_data.get("rate_limits", {})
    now_disp = datetime.now(timezone.utc)
    def _eff(limit: dict) -> float:
        rd = _parse_resets_dt(limit.get("resets_at"))
        pct = float(limit.get("used_percentage") or 0.0)
        return 0.0 if (rd and rd <= now_disp) else pct
    h5 = _eff(merged_rate.get("five_hour") or {})
    h7 = _eff(merged_rate.get("seven_day") or {})
    print(f"[Hourglass] 5h {h5:.1f}% | 7d {h7:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
