from __future__ import annotations
import json
from typing import Optional

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import config, database
from .models import UsageSnapshot
from .resources import draw_hourglass
from .ui.theme import C


def _tray_icon(pct: float) -> QIcon:
    """
    Render a 32×32 tray icon via draw_hourglass().
    Bottom sand color shifts blue → orange → red with usage level.
    """
    if pct < 50:
        bottom = C["accent_blue"]
    elif pct < 75:
        bottom = C["accent_orange"]
    else:
        bottom = C["danger"]
    return QIcon(draw_hourglass(32, usage_pct=pct, bottom_hex=bottom))


class TrayManager:
    def __init__(self, app, on_open_main=None, on_open_settings=None):
        self._app = app
        self._on_open_main = on_open_main
        self._on_open_settings = on_open_settings
        self._panel = None
        self._latest: Optional[UsageSnapshot] = None

        self._tray = QSystemTrayIcon(app)
        self._tray.setIcon(_tray_icon(0.0))
        self._tray.setToolTip("Claude Hourglass — 読み込み中...")

        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background: {C['bg_secondary']}; color: {C['text_primary']};"
            f" border: 1px solid {C['border']}; font-size: 11px; }}"
            f"QMenu::item:selected {{ background: {C['bg_tertiary']}; }}"
            f"QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 0; }}"
        )

        open_act = menu.addAction("メイン画面を開く")
        open_act.triggered.connect(self._open_main)
        settings_act = menu.addAction("設定")
        settings_act.triggered.connect(self._open_settings)
        menu.addSeparator()
        quit_act = menu.addAction("終了")
        quit_act.triggered.connect(app.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        interval = (config.get("poll_interval_sec") or 30) * 1000
        self._poll_timer.start(interval)
        self._poll()

    # ------------------------------------------------------------------

    def set_panel(self, panel) -> None:
        self._panel = panel

    def _poll(self) -> None:
        snap: Optional[UsageSnapshot] = None

        json_path = config.latest_json_path()
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                snap = UsageSnapshot.from_status_json(data)
            except Exception:
                pass

        if snap is None:
            path = config.db_path()
            if path.exists():
                snap = database.latest(path)

        self._latest = snap
        self._update_tray(snap)
        if self._panel and self._panel.isVisible():
            self._panel.update_from_snapshot(snap)

    def _update_tray(self, snap: Optional[UsageSnapshot]) -> None:
        if snap is None:
            self._tray.setToolTip("Claude Hourglass — データなし")
            self._tray.setIcon(_tray_icon(0.0))
            return

        h5 = snap.five_hour_used_pct or 0.0
        h7 = snap.seven_day_used_pct or 0.0
        self._tray.setIcon(_tray_icon(h5))

        from .ui.hourglass_panel import _format_reset
        reset_txt = _format_reset(snap.five_hour_resets_at)
        self._tray.setToolTip(
            f"Claude Hourglass\n"
            f"5h: {h5:.1f}% | 7d: {h7:.1f}%\n"
            f"リセット: {reset_txt}"
        )

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_panel()

    def _toggle_panel(self) -> None:
        if self._panel is None:
            return
        if self._panel.isVisible():
            self._panel.hide()
        else:
            self._panel.update_from_snapshot(self._latest)
            geo = self._tray.geometry()
            self._panel.show_near(QPoint(geo.right(), geo.top()))

    def _open_main(self) -> None:
        if self._on_open_main:
            self._on_open_main()

    def _open_settings(self) -> None:
        if self._on_open_settings:
            self._on_open_settings()

    def show_startup_panel(self, duration_ms: int = 4000) -> None:
        """起動時に1回だけミニパネルを表示する。"""
        if self._panel is None:
            return
        self._panel.update_from_snapshot(self._latest)
        self._panel.show_at_startup(duration_ms)

    def reload_poll_interval(self) -> None:
        interval = (config.get("poll_interval_sec") or 30) * 1000
        self._poll_timer.setInterval(interval)
