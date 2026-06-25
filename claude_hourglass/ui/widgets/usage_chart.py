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

_MSG_SINGLE = "1スナップショットのみ。履歴は Claude Code の利用に応じて蓄積されます。"
_MSG_EMPTY  = "データなし — Claude Code を使うと自動で蓄積されます。"


def _parse_dt(ts: str) -> Optional[float]:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(ts, fmt).timestamp()
        except ValueError:
            pass
    return None


def _msg_label(parent: QWidget) -> QLabel:
    lbl = QLabel("", parent)
    lbl.setFont(ui_font(9))
    lbl.setStyleSheet(f"color: {C['text_muted']}; background: transparent;")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setVisible(False)
    return lbl


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
        self._scatter: Optional[pg.ScatterPlotItem] = None
        self._hline: Optional[pg.InfiniteLine] = None
        self._msg_lbl: Optional[QLabel] = None
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
        self._plot.setLabel("left", "使用率 %", color=C["text_muted"], size="9pt")
        self._plot.getAxis("left").setStyle(tickFont=mono_font(8))
        self._plot.setYRange(0, 100, padding=0.05)
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        bottom = self._plot.getAxis("bottom")
        bottom.setStyle(tickFont=mono_font(8), tickTextHeight=36)
        bottom.setHeight(50)
        bottom.enableAutoSIPrefix(False)
        bottom.setLabel("")

        pen = pg.mkPen(color=QColor(self._color), width=2)
        fill_color = QColor(self._color)
        fill_color.setAlpha(60)
        self._curve = self._plot.plot([], [], pen=pen, fillLevel=0, brush=pg.mkBrush(fill_color))

        layout.addWidget(self._plot)

        self._msg_lbl = _msg_label(self)
        layout.addWidget(self._msg_lbl)

    def _clear_extras(self) -> None:
        if self._scatter is not None:
            self._plot.removeItem(self._scatter)
            self._scatter = None
        if self._hline is not None:
            self._plot.removeItem(self._hline)
            self._hline = None

    def load(self, snapshots: list[UsageSnapshot], field: str = "five_hour_used_pct") -> None:
        xs, ys = [], []
        for s in snapshots:
            ts = _parse_dt(s.captured_at)
            val = getattr(s, field, None)
            if ts is not None and val is not None:
                xs.append(ts)
                ys.append(float(val))

        self._clear_extras()

        if not xs:
            self._curve.setData([], [])
            self._plot.getAxis("bottom").setTicks([[]])
            self._msg_lbl.setText(_MSG_EMPTY)
            self._msg_lbl.setVisible(True)
            return

        if len(xs) == 1:
            self._curve.setData([], [])

            # Large centered marker
            dot_color = QColor(self._color)
            dot_color.setAlpha(220)
            self._scatter = pg.ScatterPlotItem(
                x=[xs[0]], y=[ys[0]],
                symbol="o", size=14,
                pen=pg.mkPen(color=QColor(self._color), width=2),
                brush=pg.mkBrush(dot_color),
            )
            self._plot.addItem(self._scatter)

            # Subtle horizontal dashed reference line
            dash_color = QColor(self._color)
            dash_color.setAlpha(80)
            self._hline = pg.InfiniteLine(
                pos=ys[0], angle=0,
                pen=pg.mkPen(color=dash_color, width=1,
                             style=Qt.PenStyle.DashLine),
            )
            self._plot.addItem(self._hline)

            # Center the single point with ±1 hour padding
            self._plot.setXRange(xs[0] - 3600, xs[0] + 3600, padding=0)

            dt = datetime.fromtimestamp(xs[0])
            self._plot.getAxis("bottom").setTicks([[(xs[0], dt.strftime("%m/%d\n%H:%M"))]])

            self._msg_lbl.setText(_MSG_SINGLE)
            self._msg_lbl.setVisible(True)
            return

        # 2+ points: normal line + fill
        self._curve.setData(xs, ys)
        self._msg_lbl.setVisible(False)

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
        self._msg_lbl: Optional[QLabel] = None
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

        self._msg_lbl = _msg_label(self)
        layout.addWidget(self._msg_lbl)

    def _set_bars(self, xs, ys, ticks, brush, pen) -> None:
        if self._bars is not None:
            self._plot.removeItem(self._bars)
        self._bars = pg.BarGraphItem(x=xs, height=ys, width=0.7, brush=brush, pen=pen)
        self._plot.addItem(self._bars)
        self._plot.getAxis("bottom").setTicks([ticks])
        self._msg_lbl.setVisible(len(xs) == 1)
        if len(xs) == 1:
            self._msg_lbl.setText(_MSG_SINGLE)

    def load_daily(self, snapshots: list[UsageSnapshot]) -> None:
        daily: dict[str, float] = {}
        for s in snapshots:
            if s.captured_at and s.five_hour_used_pct is not None:
                day = s.captured_at[:10]
                daily[day] = max(daily.get(day, 0.0), s.five_hour_used_pct)

        if not daily:
            self._msg_lbl.setText(_MSG_EMPTY)
            self._msg_lbl.setVisible(True)
            return

        sorted_days = sorted(daily.keys())
        self._set_bars(
            xs=list(range(len(sorted_days))),
            ys=[daily[d] for d in sorted_days],
            ticks=[(i, d[5:]) for i, d in enumerate(sorted_days)],
            brush=QColor(self._color),
            pen=pg.mkPen(color=QColor(self._color).darker(130), width=1),
        )

    def load_weekly(self, snapshots: list[UsageSnapshot]) -> None:
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
            self._msg_lbl.setText(_MSG_EMPTY)
            self._msg_lbl.setVisible(True)
            return

        sorted_weeks = sorted(weekly.keys())
        self._set_bars(
            xs=list(range(len(sorted_weeks))),
            ys=[weekly[w] for w in sorted_weeks],
            ticks=[(i, w.split("-W")[1] + "週") for i, w in enumerate(sorted_weeks)],
            brush=QColor(self._color).darker(110),
            pen=pg.mkPen(color=QColor(self._color).darker(140), width=1),
        )


class SessionChart(QWidget):
    """Per-session cost bars."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._bars: Optional[pg.BarGraphItem] = None
        self._plot: Optional[pg.PlotWidget] = None
        self._msg_lbl: Optional[QLabel] = None
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

        self._msg_lbl = _msg_label(self)
        layout.addWidget(self._msg_lbl)

    def load(self, snapshots: list[UsageSnapshot]) -> None:
        session_cost: dict[str, float] = {}
        for s in snapshots:
            sid = s.session_id or "unknown"
            if s.total_cost_usd is not None:
                session_cost[sid] = max(session_cost.get(sid, 0.0), s.total_cost_usd)

        if not session_cost:
            self._msg_lbl.setText(_MSG_EMPTY)
            self._msg_lbl.setVisible(True)
            return

        items = sorted(session_cost.items(), key=lambda x: x[1], reverse=True)[:20]
        xs = list(range(len(items)))
        ys = [v for _, v in items]
        ticks = [(i, sid[-6:]) for i, (sid, _) in enumerate(items)]

        if self._bars is not None:
            self._plot.removeItem(self._bars)

        self._bars = pg.BarGraphItem(
            x=xs, height=ys, width=0.7,
            brush=QColor(C["accent_blue"]),
            pen=pg.mkPen(color=QColor(C["accent_blue_dim"]), width=1),
        )
        self._plot.addItem(self._bars)
        self._plot.getAxis("bottom").setTicks([ticks])

        self._msg_lbl.setVisible(len(items) == 1)
        if len(items) == 1:
            self._msg_lbl.setText(_MSG_SINGLE)
