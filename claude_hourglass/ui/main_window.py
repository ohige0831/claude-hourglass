from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from .theme import C, mono_font, ui_font
from .widgets.current_status_tab import CurrentStatusTab
from .widgets.usage_chart import BarChart, SessionChart, TimeSeriesChart
from .. import database
from ..config import db_path
from ..resources import app_icon
from ..models import UsageSnapshot


class _Header(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(f"background: {C['bg_secondary']}; border-bottom: 1px solid {C['border']};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)

        icon_lbl = QLabel("⏳")
        icon_lbl.setFont(ui_font(18))
        icon_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(icon_lbl)

        title = QLabel("Claude Hourglass")
        title.setFont(ui_font(14, bold=True))
        title.setStyleSheet(f"color: {C['text_primary']}; background: transparent;")
        lay.addWidget(title)
        lay.addStretch()

        self._status = QLabel("")
        self._status.setFont(ui_font(10))
        self._status.setStyleSheet(f"color: {C['text_muted']}; background: transparent;")
        lay.addWidget(self._status)

    def set_status(self, text: str) -> None:
        self._status.setText(text)


class _SummaryBar(QWidget):
    """Top row of key numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {C['bg_secondary']}; border-bottom: 1px solid {C['border_subtle']};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(0)

        self._cards: dict[str, tuple[QLabel, QLabel]] = {}
        for key, label in [
            ("5h_pct", "5時間使用率"),
            ("7d_pct", "7日使用率"),
            ("cost", "累計コスト"),
            ("model", "モデル"),
        ]:
            card = QWidget()
            card.setStyleSheet("background: transparent;")
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(0, 0, 0, 0)
            card_lay.setSpacing(2)

            val_lbl = QLabel("—")
            val_lbl.setFont(mono_font(15, bold=True))
            val_lbl.setStyleSheet(f"color: {C['text_primary']}; background: transparent;")
            card_lay.addWidget(val_lbl)

            sub_lbl = QLabel(label)
            sub_lbl.setFont(ui_font(9))
            sub_lbl.setStyleSheet(f"color: {C['text_muted']}; background: transparent;")
            card_lay.addWidget(sub_lbl)

            self._cards[key] = (val_lbl, sub_lbl)

            lay.addWidget(card)
            lay.addStretch()

    def update(self, snap: Optional[UsageSnapshot]) -> None:  # type: ignore[override]
        if snap is None:
            return

        def color(p: float) -> str:
            if p >= 75:
                return C["danger"]
            if p >= 50:
                return C["accent_orange"]
            return C["accent_blue"]

        h5 = snap.five_hour_used_pct or 0.0
        h7 = snap.seven_day_used_pct or 0.0
        cost = snap.total_cost_usd

        self._cards["5h_pct"][0].setText(f"{h5:.1f}%")
        self._cards["5h_pct"][0].setStyleSheet(
            f"color: {color(h5)}; background: transparent; font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: bold;"
        )
        self._cards["7d_pct"][0].setText(f"{h7:.1f}%")
        self._cards["7d_pct"][0].setStyleSheet(
            f"color: {color(h7)}; background: transparent; font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: bold;"
        )
        if cost is not None:
            self._cards["cost"][0].setText(f"${cost:.4f}")
        self._cards["model"][0].setText(snap.model_display_name or "—")
        self._cards["model"][0].setStyleSheet(
            f"color: {C['text_secondary']}; background: transparent;"
            f" font-family: 'IBM Plex Sans JP', sans-serif; font-size: 12px;"
        )


class MainWindow(QMainWindow):
    def __init__(self, on_settings=None, parent=None):
        super().__init__(parent)
        self._on_settings = on_settings
        self.setWindowTitle("Claude Hourglass")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(780, 560)
        self.resize(900, 640)

        self._header = _Header()
        self._summary = _SummaryBar()
        self._tabs: Optional[QTabWidget] = None
        self._current_tab: Optional[CurrentStatusTab] = None
        self._chart_5h: Optional[TimeSeriesChart] = None
        self._chart_7d: Optional[TimeSeriesChart] = None
        self._chart_daily: Optional[BarChart] = None
        self._chart_weekly: Optional[BarChart] = None
        self._chart_session: Optional[SessionChart] = None

        self._build()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_charts)
        self._refresh_timer.start(60_000)

    # ------------------------------------------------------------------

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._header)
        root.addWidget(self._summary)

        # Main content area
        content = QWidget()
        content.setStyleSheet(f"background: {C['bg_primary']};")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(16, 16, 16, 16)
        content_lay.setSpacing(8)

        # Tab bar
        self._tabs = QTabWidget()
        content_lay.addWidget(self._tabs)

        # ---------- Tab: 現在 ----------
        tab_current = QWidget()
        tab_current.setStyleSheet(f"background: {C['bg_secondary']};")
        tc_lay = QVBoxLayout(tab_current)
        tc_lay.setContentsMargins(12, 12, 12, 4)
        self._current_tab = CurrentStatusTab(on_refresh=self.refresh_charts)
        tc_lay.addWidget(self._current_tab)
        self._tabs.addTab(tab_current, "現在")

        # ---------- Tab: 5時間制限 ----------
        tab_5h = QWidget()
        tab_5h.setStyleSheet(f"background: {C['bg_secondary']};")
        t5_lay = QVBoxLayout(tab_5h)
        t5_lay.setContentsMargins(12, 12, 12, 4)
        self._chart_5h = TimeSeriesChart("5時間制限 使用率推移", C["accent_orange"])
        t5_lay.addWidget(self._chart_5h)
        self._tabs.addTab(tab_5h, "5時間制限")

        # ---------- Tab: 7日制限 ----------
        tab_7d = QWidget()
        tab_7d.setStyleSheet(f"background: {C['bg_secondary']};")
        t7_lay = QVBoxLayout(tab_7d)
        t7_lay.setContentsMargins(12, 12, 12, 4)
        self._chart_7d = TimeSeriesChart("7日制限 使用率推移", C["accent_blue"])
        t7_lay.addWidget(self._chart_7d)
        self._tabs.addTab(tab_7d, "7日制限")

        # ---------- Tab: 日別 ----------
        tab_day = QWidget()
        tab_day.setStyleSheet(f"background: {C['bg_secondary']};")
        td_lay = QVBoxLayout(tab_day)
        td_lay.setContentsMargins(12, 12, 12, 4)
        self._chart_daily = BarChart("日別ピーク使用率 (5時間枠)", C["accent_amber"])
        td_lay.addWidget(self._chart_daily)
        self._tabs.addTab(tab_day, "日別")

        # ---------- Tab: 週別 ----------
        tab_week = QWidget()
        tab_week.setStyleSheet(f"background: {C['bg_secondary']};")
        tw_lay = QVBoxLayout(tab_week)
        tw_lay.setContentsMargins(12, 12, 12, 4)
        self._chart_weekly = BarChart("週別ピーク使用率 (5時間枠)", C["accent_orange"])
        tw_lay.addWidget(self._chart_weekly)
        self._tabs.addTab(tab_week, "週別")

        # ---------- Tab: セッション ----------
        tab_sess = QWidget()
        tab_sess.setStyleSheet(f"background: {C['bg_secondary']};")
        ts_lay = QVBoxLayout(tab_sess)
        ts_lay.setContentsMargins(12, 12, 12, 4)
        self._chart_session = SessionChart()
        ts_lay.addWidget(self._chart_session)
        self._tabs.addTab(tab_sess, "セッション")

        root.addWidget(content, 1)

        # Bottom bar
        bottom = QWidget()
        bottom.setFixedHeight(40)
        bottom.setStyleSheet(
            f"background: {C['bg_secondary']}; border-top: 1px solid {C['border']};"
        )
        bottom_lay = QHBoxLayout(bottom)
        bottom_lay.setContentsMargins(16, 0, 16, 0)

        refresh_btn = QPushButton("更新")
        refresh_btn.setFont(ui_font(10))
        refresh_btn.clicked.connect(self.refresh_charts)
        bottom_lay.addWidget(refresh_btn)
        bottom_lay.addStretch()

        settings_btn = QPushButton("設定")
        settings_btn.setFont(ui_font(10))
        settings_btn.clicked.connect(self._emit_settings)
        bottom_lay.addWidget(settings_btn)

        root.addWidget(bottom)

    # ------------------------------------------------------------------

    def refresh_charts(self) -> None:
        path = db_path()
        if not path.exists():
            self._header.set_status("データなし — サンプルデータを生成してください")
            return

        snapshots = database.recent(path, days=30)
        latest = database.latest(path)

        self._summary.update(latest)

        if self._current_tab:
            self._current_tab.update_snapshot(latest)

        if self._chart_5h:
            self._chart_5h.load(snapshots, "five_hour_used_pct")
        if self._chart_7d:
            self._chart_7d.load(snapshots, "seven_day_used_pct")
        if self._chart_daily:
            self._chart_daily.load_daily(snapshots)
        if self._chart_weekly:
            self._chart_weekly.load_weekly(snapshots)
        if self._chart_session:
            self._chart_session.load(snapshots)

        count = len(snapshots)
        self._header.set_status(f"{count} スナップショット (直近30日)")

    def _emit_settings(self) -> None:
        if self._on_settings:
            self._on_settings()

    def closeEvent(self, event: QCloseEvent) -> None:
        # Hide instead of close so tray icon keeps working
        event.ignore()
        self.hide()
