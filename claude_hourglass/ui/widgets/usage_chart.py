from __future__ import annotations
from datetime import datetime
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..theme import C, mono_font, ui_font
from ...models import UsageSnapshot

pg.setConfigOption("background", C["bg_secondary"])
pg.setConfigOption("foreground", C["text_muted"])


def _parse_dt(ts: str) -> Optional[float]:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(ts, fmt).timestamp()
        except ValueError:
            pass
    return None


class TimeSeriesChart(QWidget):
    """Line chart for a single percentage metric over time."""

    def __init__(
        self,
        title: str,
        color: str = C["accent_orange"],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._color = color
        self._title = title
        self._plot: Optional[pg.PlotWidget] = None
        self._curve: Optional[pg.PlotDataItem] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        # 下に余白を持たせてラベルがウィジェット境界でクリップされないようにする
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(4)

        lbl = QLabel(self._title)
        lbl.setFont(ui_font(10))
        lbl.setStyleSheet(f"color: {C['text_secondary']}; background: transparent;")
        layout.addWidget(lbl)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(C["bg_secondary"])
        self._plot.showGrid(x=False, y=True, alpha=0.15)
        self._plot.setLabel("left", "使用率 %", color=C["text_muted"], size="9pt")
        self._plot.getAxis("left").setStyle(tickFont=mono_font(8))
        self._plot.setYRange(0, 100, padding=0.05)
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Bottom axis: 2行ラベル (MM/DD + HH:mm) が切れないよう高さを確保する
        #   tickTextHeight: 1行 ≈ 11px、2行 = 22px + 余白 → 36px
        #   setHeight: AxisItem がレイアウトに要求する総高さ (tick + offset + text)
        bottom = self._plot.getAxis("bottom")
        bottom.setStyle(tickFont=mono_font(8), tickTextHeight=36)
        bottom.setHeight(50)
        bottom.enableAutoSIPrefix(False)
        bottom.setLabel("")  # SI prefix を出さない; ラベルは setTicks() で設定

        pen = pg.mkPen(color=QColor(self._color), width=2)
        fill_color = QColor(self._color)
        fill_color.setAlpha(60)
        fill = pg.mkBrush(fill_color)
        self._curve = self._plot.plot([], [], pen=pen, fillLevel=0, brush=fill)

        layout.addWidget(self._plot)

    def load(self, snapshots: list[UsageSnapshot], field: str = "five_hour_used_pct") -> None:
        xs, ys = [], []
        for s in snapshots:
            ts = _parse_dt(s.captured_at)
            val = getattr(s, field, None)
            if ts is not None and val is not None:
                xs.append(ts)
                ys.append(float(val))

        if self._curve:
            self._curve.setData(xs, ys)

        if self._plot and xs:
            # Format x-axis as HH:MM
            ticks = []
            step = max(1, len(xs) // 6)
            for i in range(0, len(xs), step):
                dt = datetime.fromtimestamp(xs[i])
                ticks.append((xs[i], dt.strftime("%m/%d\n%H:%M")))
            self._plot.getAxis("bottom").setTicks([ticks])


class BarChart(QWidget):
    """Bar chart showing daily/weekly peak usage."""

    def __init__(
        self,
        title: str,
        color: str = C["accent_amber"],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._color = color
        self._title = title
        self._bars: Optional[pg.BarGraphItem] = None
        self._plot: Optional[pg.PlotWidget] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(4)

        lbl = QLabel(self._title)
        lbl.setFont(ui_font(10))
        lbl.setStyleSheet(f"color: {C['text_secondary']}; background: transparent;")
        layout.addWidget(lbl)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(C["bg_secondary"])
        self._plot.showGrid(x=False, y=True, alpha=0.15)
        self._plot.setLabel("left", "ピーク使用率 %", color=C["text_muted"], size="9pt")
        self._plot.getAxis("left").setStyle(tickFont=mono_font(8))
        bottom = self._plot.getAxis("bottom")
        bottom.setStyle(tickFont=mono_font(8), tickTextHeight=18)
        bottom.setHeight(32)
        self._plot.setYRange(0, 100, padding=0.05)
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._plot)

    def load_daily(self, snapshots: list[UsageSnapshot]) -> None:
        """Aggregate snapshots by day (peak five_hour_used_pct per day)."""
        daily: dict[str, float] = {}
        for s in snapshots:
            if s.captured_at and s.five_hour_used_pct is not None:
                day = s.captured_at[:10]
                daily[day] = max(daily.get(day, 0.0), s.five_hour_used_pct)

        if not daily:
            return

        sorted_days = sorted(daily.keys())
        xs = list(range(len(sorted_days)))
        ys = [daily[d] for d in sorted_days]
        ticks = [(i, d[5:]) for i, d in enumerate(sorted_days)]  # MM-DD

        if self._bars:
            self._plot.removeItem(self._bars)  # type: ignore[union-attr]

        self._bars = pg.BarGraphItem(
            x=xs,
            height=ys,
            width=0.7,
            brush=QColor(self._color),
            pen=pg.mkPen(color=QColor(self._color).darker(130), width=1),
        )
        if self._plot:
            self._plot.addItem(self._bars)
            self._plot.getAxis("bottom").setTicks([ticks])

    def load_weekly(self, snapshots: list[UsageSnapshot]) -> None:
        """Aggregate by ISO week."""
        weekly: dict[str, float] = {}
        for s in snapshots:
            if s.captured_at and s.five_hour_used_pct is not None:
                try:
                    dt = datetime.fromisoformat(s.captured_at.rstrip("Z"))
                    week = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
                    weekly[week] = max(weekly.get(week, 0.0), s.five_hour_used_pct)
                except ValueError:
                    pass

        if not weekly:
            return

        sorted_weeks = sorted(weekly.keys())
        xs = list(range(len(sorted_weeks)))
        ys = [weekly[w] for w in sorted_weeks]
        ticks = [(i, w.split("-W")[1] + "週") for i, w in enumerate(sorted_weeks)]

        if self._bars:
            self._plot.removeItem(self._bars)  # type: ignore[union-attr]

        self._bars = pg.BarGraphItem(
            x=xs,
            height=ys,
            width=0.7,
            brush=QColor(self._color).darker(110),
            pen=pg.mkPen(color=QColor(self._color).darker(140), width=1),
        )
        if self._plot:
            self._plot.addItem(self._bars)
            self._plot.getAxis("bottom").setTicks([ticks])


class SessionChart(QWidget):
    """Per-session cost bars."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._bars: Optional[pg.BarGraphItem] = None
        self._plot: Optional[pg.PlotWidget] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(4)

        lbl = QLabel("セッション別コスト (USD)")
        lbl.setFont(ui_font(10))
        lbl.setStyleSheet(f"color: {C['text_secondary']}; background: transparent;")
        layout.addWidget(lbl)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(C["bg_secondary"])
        self._plot.showGrid(x=False, y=True, alpha=0.15)
        self._plot.setLabel("left", "コスト USD", color=C["text_muted"], size="9pt")
        self._plot.getAxis("left").setStyle(tickFont=mono_font(8))
        bottom = self._plot.getAxis("bottom")
        bottom.setStyle(tickFont=mono_font(8), tickTextHeight=18)
        bottom.setHeight(32)
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._plot)

    def load(self, snapshots: list[UsageSnapshot]) -> None:
        """Show max cost per session (as proxy for session total)."""
        session_cost: dict[str, float] = {}
        for s in snapshots:
            sid = s.session_id or "unknown"
            if s.total_cost_usd is not None:
                session_cost[sid] = max(session_cost.get(sid, 0.0), s.total_cost_usd)

        if not session_cost:
            return

        items = sorted(session_cost.items(), key=lambda x: x[1], reverse=True)[:20]
        xs = list(range(len(items)))
        ys = [v for _, v in items]
        ticks = [(i, sid[-6:]) for i, (sid, _) in enumerate(items)]

        if self._bars:
            self._plot.removeItem(self._bars)  # type: ignore[union-attr]

        self._bars = pg.BarGraphItem(
            x=xs,
            height=ys,
            width=0.7,
            brush=QColor(C["accent_blue"]),
            pen=pg.mkPen(color=QColor(C["accent_blue_dim"]), width=1),
        )
        if self._plot:
            self._plot.addItem(self._bars)
            self._plot.getAxis("bottom").setTicks([ticks])
