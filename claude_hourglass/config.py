from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path.home() / ".claude_hourglass"

DEFAULTS: dict[str, Any] = {
    "db_path": str(_DEFAULT_DIR / "usage.sqlite"),
    "latest_json_path": str(_DEFAULT_DIR / "latest_usage.json"),
    "latest_statusline_raw_path": str(_DEFAULT_DIR / "latest_statusline_raw.json"),
    "latest_official_ui_path": str(_DEFAULT_DIR / "latest_official_ui.json"),
    "poll_interval_sec": 30,
    "theme": "dark",
    "window_opacity": 0.95,
    # 起動時ミニパネル表示 (True = 表示する)
    "show_startup_panel": True,
    # ローカル受信 HTTP サーバー
    "receiver_enabled": True,
    "receiver_port": 43871,
    # alt source として表示する最大経過秒数 (デフォルト 10分)
    "alt_max_age_secs": 600,
    # 公式UI WebView 収集
    "official_webview_enabled": False,
    "official_webview_interval_secs": 60,
    "official_webview_profile_dir": str(_DEFAULT_DIR / "webview_profile"),
    "official_usage_url": "https://claude.ai/settings/usage",
    # 自動起動の真の状態は startup.is_startup_enabled() で読むこと (レジストリが正)
}

_CONFIG_PATH = _DEFAULT_DIR / "config.json"
_cache: dict[str, Any] = {}


def _ensure_dir() -> None:
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict[str, Any]:
    global _cache
    _ensure_dir()
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            _cache = {**DEFAULTS, **data}
        except Exception:
            _cache = dict(DEFAULTS)
    else:
        _cache = dict(DEFAULTS)
    return _cache


def get(key: str) -> Any:
    if not _cache:
        load()
    return _cache.get(key, DEFAULTS.get(key))


def set(key: str, value: Any) -> None:
    if not _cache:
        load()
    _cache[key] = value
    save()


def save() -> None:
    _ensure_dir()
    _CONFIG_PATH.write_text(
        json.dumps(_cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def db_path() -> Path:
    return Path(get("db_path"))


def latest_json_path() -> Path:
    return Path(get("latest_json_path"))


def statusline_raw_path() -> Path:
    return Path(get("latest_statusline_raw_path"))


def official_ui_path() -> Path:
    return Path(get("latest_official_ui_path"))


def webview_status_path() -> Path:
    return _DEFAULT_DIR / "official_webview_status.json"


def webview_profile_dir() -> Path:
    return Path(get("official_webview_profile_dir"))
