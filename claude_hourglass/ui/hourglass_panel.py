from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .theme import C, mono_font, ui_font, qc
from .widgets.hourglass_widget import HourglassWidget
from ..models import UsageSnapshot


class _Separator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setStyleSheet(f"color: {C['border']}; background: {C['border']};")
        self.setFixedHeight(1)


class _StatRow(QWidget):
    """One metric row: label + value."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._lbl = QLabel(label)
        self._lbl.setFont(ui_font(10))
        self._lbl.setStyleSheet(f"color: {C['text_muted']}; background: transparent;")
        self._lbl.setFixedWidth(90)

        self._val = QLabel("—")
        self._val.setFont(mono_font(11))
        self._val.setStyleSheet(f"color: {C['text_primary']}; background: transparent;")

        lay.addWidget(self._lbl)
        lay.addWidget(self._val, 1)

    def set_value(self, text, color: str = C["text_primary"]) -> None:
        self._val.setText(str(text))
        self._val.setStyleSheet(f"color: {color}; background: transparent;")


class HourglassPanel(QWidget):
    """
    Small floating panel shown when tray icon is left-clicked.
    Displays the hourglass animation plus key usage metrics.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowOpacity(0.97)
        self._build()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.setStyleSheet(
            f"QWidget {{ background: {C['bg_panel']}; }}"
            f"QWidget#panel {{ border: 1px solid {C['border']}; border-radius: 4px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        panel = QWidget(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(
            f"background: {C['bg_panel']}; border: 1px solid {C['border']}; border-radius: 4px;"
        )
        outer.addWidget(panel)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # Title bar
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = QLabel("Claude Hourglass")
        title.setFont(ui_font(11, bold=True))
        title.setStyleSheet(f"color: {C['text_primary']}; background: transparent;")
        title_row.addWidget(title, 1)

        close_btn = QPushButton("×")
        close_btn.setFont(ui_font(13))
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {C['text_muted']};"
            f" border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {C['text_primary']}; }}"
        )
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(close_btn)

        lay.addLayout(title_row)
        lay.addWidget(_Separator())

        # Content: hourglass + stats side by side
        content = QHBoxLayout()
        content.setSpacing(16)

        self._hourglass = HourglassWidget(self)
        content.addWidget(self._hourglass, 0, Qt.AlignTop)

        stats_col = QVBoxLayout()
        stats_col.setSpacing(4)

        # 5-hour row
        h5_head = QLabel("5時間制限")
        h5_head.setFont(ui_font(9))
        h5_head.setStyleSheet(f"color: {C['text_muted']}; background: transparent;")
        stats_col.addWidget(h5_head)

        self._row_5h_pct = _StatRow("使用率")
        self._row_5h_reset = _StatRow("リセット")
        stats_col.addWidget(self._row_5h_pct)
        stats_col.addWidget(self._row_5h_reset)
        stats_col.addSpacing(6)

        # 7-day row
        h7_head = QLabel("7日制限")
        h7_head.setFont(ui_font(9))
        h7_head.setStyleSheet(f"color: {C['text_muted']}; background: transparent;")
        stats_col.addWidget(h7_head)

        self._row_7d_pct = _StatRow("使用率")
        self._row_7d_reset = _StatRow("リセット")
        stats_col.addWidget(self._row_7d_pct)
        stats_col.addWidget(self._row_7d_reset)
        stats_col.addSpacing(6)

        # Cost / model
        self._row_cost = _StatRow("コスト")
        self._row_model = _StatRow("モデル")
        stats_col.addWidget(_Separator())
        stats_col.addSpacing(4)
        stats_col.addWidget(self._row_cost)
        stats_col.addWidget(self._row_model)
        stats_col.addStretch()

        content.addLayout(stats_col, 1)
        lay.addLayout(content)

        # Last updated
        lay.addWidget(_Separator())
        self._updated_lbl = QLabel("最終更新: —")
        self._updated_lbl.setFont(ui_font(9))
        self._updated_lbl.setStyleSheet(f"color: {C['text_muted']}; background: transparent;")
        lay.addWidget(self._updated_lbl)

        self.setFixedWidth(360)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def update_from_snapshot(self, snap: Optional[UsageSnapshot]) -> None:
        if snap is None:
            self._hourglass.set_usage(0.0, 0.0)
            return

        h5 = snap.five_hour_used_pct or 0.0
        h7 = snap.seven_day_used_pct or 0.0
        self._hourglass.set_usage(h5, h7)

        def pct_color(p: float) -> str:
            if p >= 75:
                return C["danger"]
            if p >= 50:
                return C["accent_orange"]
            return C["text_primary"]

        self._row_5h_pct.set_value(f"{h5:.1f}%", pct_color(h5))
        self._row_7d_pct.set_value(f"{h7:.1f}%", pct_color(h7))

        self._row_5h_reset.set_value(
            _format_reset(snap.five_hour_resets_at), C["text_secondary"]
        )
        self._row_7d_reset.set_value(
            _format_reset(snap.seven_day_resets_at), C["text_secondary"]
        )

        if snap.total_cost_usd is not None:
            self._row_cost.set_value(f"${snap.total_cost_usd:.4f}")
        else:
            self._row_cost.set_value("—")

        self._row_model.set_value(snap.model_display_name or "—")

        try:
            ts = datetime.fromisoformat(snap.captured_at.rstrip("Z")).replace(
                tzinfo=timezone.utc
            )
            local = ts.astimezone()
            self._updated_lbl.setText(f"最終更新: {local.strftime('%H:%M:%S')}")
        except Exception:
            self._updated_lbl.setText(f"最終更新: {snap.captured_at}")

    def show_near(self, anchor: QPoint) -> None:
        self.adjustSize()
        self.move(anchor.x() - self.width() - 8, anchor.y() - self.height() - 8)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_at_startup(self, duration_ms: int = 4000) -> None:
        """起動時に画面右下へ表示し、duration_ms 後に自動で閉じる。"""
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        margin = 16
        x = screen.right() - self.width() - margin
        y = screen.bottom() - self.height() - margin
        self.move(x, y)
        self.show()
        self.raise_()
        QTimer.singleShot(duration_ms, self.hide)


def _format_reset(resets_at) -> str:
    """resets_at を '4h 23m (17:00)' 形式に変換する。int/float はエポック秒として扱う。"""
    if resets_at is None:
        return "—"
    try:
        # Unix epoch int/float → datetime
        if isinstance(resets_at, (int, float)):
            dt = datetime.fromtimestamp(int(resets_at), tz=timezone.utc)
        else:
            dt = None
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(str(resets_at), fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    pass
            if dt is None:
                return str(resets_at)

        total_secs = int((dt - datetime.now(timezone.utc)).total_seconds())
        if total_secs <= 0:
            return "リセット済み"
        hours, rem = divmod(total_secs, 3600)
        local = dt.astimezone()
        return f"{hours}h {rem // 60:02d}m ({local.strftime('%H:%M')})"
    except Exception:
        return str(resets_at)
