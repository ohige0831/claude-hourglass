from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QFont
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import config, database
from .models import UsageSnapshot
from .ui.theme import C, qc


def _make_tray_icon(pct: float) -> QIcon:
    """
    Render a 32×32 pixel-art hourglass icon.
    Color shifts from blue → orange → red based on usage percentage.
    """
    size = 32
    px = QPixmap(size, size)
    px.fill(QColor(0, 0, 0, 0))

    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing, False)

    if pct < 50:
        sand_color = QColor(C["accent_blue"])
    elif pct < 75:
        sand_color = QColor(C["accent_orange"])
    else:
        sand_color = QColor(C["danger"])

    bg = QColor(C["bg_primary"])
    outline = QColor(C["border"])
    cream = QColor(C["sand_full"])

    # Hourglass body outline (pixel art, 32×32)
    # Simplified: two triangles + waist
    W, H = size, size
    cx = W // 2

    for y in range(H):
        if y < H // 2:
            # top half: taper from W to 4
            t = y / (H // 2)
            w = max(4, round(W - t * (W - 4)))
        else:
            # bottom half: expand from 4 to W
            t = (y - H // 2) / (H // 2)
            w = max(4, round(4 + t * (W - 4)))
        x0 = cx - w // 2
        x1 = cx + w // 2

        for x in range(x0, x1 + 1):
            used = pct / 100.0
            if y < H // 2:
                # Top: cream dots for remaining, bg for used
                fill_boundary = round((H // 2) * (1 - used))
                color = cream if y < fill_boundary else bg
            else:
                # Bottom: sand_color for used, bg for empty
                fill_boundary = H - round((H // 2) * used)
                color = sand_color if y >= fill_boundary else bg
            painter.fillRect(x, y, 1, 1, color)

    # Draw outline dots on hourglass edges
    for y in range(H):
        if y < H // 2:
            t = y / (H // 2)
            w = max(4, round(W - t * (W - 4)))
        else:
            t = (y - H // 2) / (H // 2)
            w = max(4, round(4 + t * (W - 4)))
        x0 = cx - w // 2
        x1 = cx + w // 2
        painter.fillRect(x0, y, 1, 1, outline)
        painter.fillRect(x1, y, 1, 1, outline)

    painter.end()
    return QIcon(px)


class TrayManager:
    def __init__(self, app, on_open_main=None, on_open_settings=None):
        self._app = app
        self._on_open_main = on_open_main
        self._on_open_settings = on_open_settings
        self._panel = None
        self._latest: Optional[UsageSnapshot] = None

        self._tray = QSystemTrayIcon(app)
        self._tray.setIcon(_make_tray_icon(0.0))
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

        # Poll timer
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        interval = (config.get("poll_interval_sec") or 30) * 1000
        self._poll_timer.start(interval)
        self._poll()  # immediate first poll

    # ------------------------------------------------------------------

    def set_panel(self, panel) -> None:
        self._panel = panel

    def _poll(self) -> None:
        # Try latest_usage.json first (fastest)
        json_path = config.latest_json_path()
        snap: Optional[UsageSnapshot] = None

        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                snap = UsageSnapshot.from_status_json(data)
            except Exception:
                pass

        # Fallback to DB
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
            self._tray.setIcon(_make_tray_icon(0.0))
            return

        h5 = snap.five_hour_used_pct or 0.0
        h7 = snap.seven_day_used_pct or 0.0
        self._tray.setIcon(_make_tray_icon(h5))

        from .ui.hourglass_panel import _format_reset
        reset_txt = _format_reset(snap.five_hour_resets_at)
        tooltip = (
            f"Claude Hourglass\n"
            f"5h: {h5:.1f}% | 7d: {h7:.1f}%\n"
            f"リセット: {reset_txt}"
        )
        self._tray.setToolTip(tooltip)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # left click
            self._toggle_panel()

    def _toggle_panel(self) -> None:
        if self._panel is None:
            return
        if self._panel.isVisible():
            self._panel.hide()
        else:
            self._panel.update_from_snapshot(self._latest)
            geo = self._tray.geometry()
            anchor = QPoint(geo.right(), geo.top())
            self._panel.show_near(anchor)

    def _open_main(self) -> None:
        if self._on_open_main:
            self._on_open_main()

    def _open_settings(self) -> None:
        if self._on_open_settings:
            self._on_open_settings()

    def reload_poll_interval(self) -> None:
        interval = (config.get("poll_interval_sec") or 30) * 1000
        self._poll_timer.setInterval(interval)
