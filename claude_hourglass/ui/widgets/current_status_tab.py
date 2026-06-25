from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from ..theme import C, mono_font, ui_font
from .hourglass_widget import HourglassWidget
from ...models import UsageSnapshot


class _LargeHourglassWidget(HourglassWidget):
    """Scale-up of HourglassWidget for the main window (6px dots)."""
    DOT = 6
    GAP = 1
    CELL = DOT + GAP  # 7px/cell → 154×252px


class _Card(QWidget):
    """Stat card with title heading and labeled value rows."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self.setStyleSheet(
            "QWidget#stat_card {"
            f"  background: {C['bg_tertiary']};"
            f"  border: 1px solid {C['border']};"
            "  border-radius: 6px;"
            "}"
        )
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(14, 10, 14, 10)
        self._inner.setSpacing(5)

        heading = QLabel(title)
        heading.setFont(ui_font(9))
        heading.setStyleSheet(f"color: {C['text_muted']}; background: transparent; border: none;")
        self._inner.addWidget(heading)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C['border_subtle']}; border: none;")
        self._inner.addWidget(sep)

    def add_row(self, label: str, font_size: int = 11) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFont(ui_font(9))
        lbl.setStyleSheet(f"color: {C['text_muted']}; background: transparent; border: none;")
        lbl.setFixedWidth(90)
        val = QLabel("—")
        val.setFont(mono_font(font_size))
        val.setStyleSheet(f"color: {C['text_primary']}; background: transparent; border: none;")
        row.addWidget(lbl)
        row.addWidget(val, 1)
        self._inner.addLayout(row)
        return val


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct_color(p: float) -> str:
    if p >= 75:
        return C["danger"]
    if p >= 50:
        return C["accent_orange"]
    return C["text_primary"]


def _fmt_countdown(resets_at: Optional[str]) -> str:
    """'Xh Ym' remaining, or 'リセット済み'."""
    if not resets_at:
        return "—"
    try:
        dt = _parse_utc(resets_at)
        if dt is None:
            return "—"
        secs = int((dt - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "リセット済み"
        h, rem = divmod(secs, 3600)
        return f"{h}h {rem // 60:02d}m"
    except Exception:
        return "—"


def _fmt_local_time(resets_at: Optional[str]) -> str:
    """Local time string 'MM/DD HH:MM'."""
    if not resets_at:
        return "—"
    try:
        dt = _parse_utc(resets_at)
        if dt is None:
            return "—"
        return dt.astimezone().strftime("%m/%d %H:%M")
    except Exception:
        return "—"


def _parse_utc(ts) -> Optional[datetime]:
    """ISO 文字列またはエポック秒 (int/float) を UTC datetime に変換する。"""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(str(ts), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class CurrentStatusTab(QWidget):
    """「現在」タブ — 大きな砂時計 + 現在の使用状況カード。"""

    def __init__(self, on_refresh=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._on_refresh = on_refresh
        self._build()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        content = QHBoxLayout()
        content.setSpacing(24)

        # ---- Left: large hourglass ----
        self._hourglass = _LargeHourglassWidget(self)
        content.addWidget(self._hourglass, 0, Qt.AlignTop)

        # ---- Right: stat cards + refresh button ----
        right = QVBoxLayout()
        right.setSpacing(8)

        # 5時間制限
        card5 = _Card("5時間制限")
        self._v5_pct = card5.add_row("使用率", 14)
        self._v5_countdown = card5.add_row("リセットまで", 11)
        self._v5_time = card5.add_row("リセット時刻", 11)
        right.addWidget(card5)

        # 7日制限
        card7 = _Card("7日制限")
        self._v7_pct = card7.add_row("使用率", 14)
        self._v7_countdown = card7.add_row("リセットまで", 11)
        self._v7_time = card7.add_row("リセット時刻", 11)
        right.addWidget(card7)

        # その他
        card_other = _Card("その他")
        self._v_cost = card_other.add_row("累計コスト", 11)
        self._v_model = card_other.add_row("モデル", 10)
        self._v_updated = card_other.add_row("最終更新", 10)
        right.addWidget(card_other)

        right.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("更新")
        refresh_btn.setFont(ui_font(10))
        refresh_btn.clicked.connect(self._do_refresh)
        btn_row.addWidget(refresh_btn)
        right.addLayout(btn_row)

        content.addLayout(right, 1)
        root.addLayout(content, 1)

    # ------------------------------------------------------------------

    def _do_refresh(self) -> None:
        if self._on_refresh:
            self._on_refresh()

    def update_snapshot(self, snap: Optional[UsageSnapshot]) -> None:
        if snap is None:
            self._hourglass.set_usage(0.0, 0.0)
            return

        h5 = snap.five_hour_used_pct or 0.0
        h7 = snap.seven_day_used_pct or 0.0
        self._hourglass.set_usage(h5, h7)

        # 5時間制限
        self._v5_pct.setText(f"{h5:.1f}%")
        self._v5_pct.setStyleSheet(
            f"color: {_pct_color(h5)}; background: transparent; border: none;"
            f" font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: bold;"
        )
        self._v5_countdown.setText(_fmt_countdown(snap.five_hour_resets_at))
        self._v5_time.setText(_fmt_local_time(snap.five_hour_resets_at))

        # 7日制限
        self._v7_pct.setText(f"{h7:.1f}%")
        self._v7_pct.setStyleSheet(
            f"color: {_pct_color(h7)}; background: transparent; border: none;"
            f" font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: bold;"
        )
        self._v7_countdown.setText(_fmt_countdown(snap.seven_day_resets_at))
        self._v7_time.setText(_fmt_local_time(snap.seven_day_resets_at))

        # その他
        if snap.total_cost_usd is not None:
            self._v_cost.setText(f"${snap.total_cost_usd:.4f}")
        else:
            self._v_cost.setText("—")

        self._v_model.setText(snap.model_display_name or "—")

        try:
            dt = _parse_utc(snap.captured_at)
            if dt:
                self._v_updated.setText(dt.astimezone().strftime("%H:%M:%S"))
            else:
                self._v_updated.setText(snap.captured_at)
        except Exception:
            self._v_updated.setText(snap.captured_at or "—")
