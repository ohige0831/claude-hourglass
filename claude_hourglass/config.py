from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path.home() / ".claude_hourglass"

DEFAULTS: dict[str, Any] = {
    "db_path": str(_DEFAULT_DIR / "usage.sqlite"),
    "latest_json_path": str(_DEFAULT_DIR / "latest_usage.json"),
    "poll_interval_sec": 30,
    "theme": "dark",
    "window_opacity": 0.95,
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
