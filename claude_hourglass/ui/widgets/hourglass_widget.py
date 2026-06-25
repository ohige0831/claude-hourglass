from __future__ import annotations
import math
import random
from typing import Optional

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..theme import C, qc, sand_color


class HourglassWidget(QWidget):
    """
    Pixel-art style hourglass.

    Dots arranged in a tapered grid: top half shows remaining capacity
    (cream), bottom half shows consumed usage (amber→red).
    A small number of particles fall through the waist for subtle motion.
    """

    # Grid parameters
    COLS = 22
    ROWS = 36
    WAIST_COLS = 4
    WAIST_ROWS = 2
    DOT = 4         # dot size in px
    GAP = 1         # gap between dots
    CELL = DOT + GAP  # 5px per cell

    # Particle system
    MAX_PARTICLES = 4

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._five_hour_pct: float = 0.0
        self._seven_day_pct: float = 0.0
        self._tick: int = 0
        self._particles: list[dict] = []

        w = self.COLS * self.CELL
        h = self.ROWS * self.CELL
        self.setFixedSize(w, h)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(80)  # ~12fps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_usage(self, five_hour_pct: float, seven_day_pct: float = 0.0) -> None:
        self._five_hour_pct = max(0.0, min(100.0, five_hour_pct))
        self._seven_day_pct = max(0.0, min(100.0, seven_day_pct))
        self.update()

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _col_range(self, row: int) -> tuple[int, int]:
        """Returns (start_col, exclusive_end_col) for the hourglass at *row*."""
        half = self.ROWS // 2
        waist_start = (self.COLS - self.WAIST_COLS) // 2

        if row <= half - self.WAIST_ROWS:
            # Top half: taper from full width down to waist
            t = row / max(1, half - self.WAIST_ROWS)
            w = round(self.COLS - t * (self.COLS - self.WAIST_COLS))
            w = max(w, self.WAIST_COLS)
        elif row >= half + self.WAIST_ROWS:
            # Bottom half: expand from waist back to full width
            t = (row - half - self.WAIST_ROWS) / max(1, self.ROWS - half - self.WAIST_ROWS)
            w = round(self.WAIST_COLS + t * (self.COLS - self.WAIST_COLS))
            w = max(w, self.WAIST_COLS)
        else:
            w = self.WAIST_COLS

        start = (self.COLS - w) // 2
        return start, start + w

    # ------------------------------------------------------------------
    # Particle helpers
    # ------------------------------------------------------------------

    def _spawn_particle(self) -> dict:
        waist_center = self.COLS // 2
        waist_start = (self.COLS - self.WAIST_COLS) // 2
        col = waist_start + random.randint(0, self.WAIST_COLS - 1)
        top_rows = (self.ROWS // 2) - self.WAIST_ROWS
        return {"row": float(random.randint(max(0, top_rows - 8), top_rows - 1)),
                "col": float(col),
                "speed": 0.4 + random.random() * 0.3}

    def _advance(self) -> None:
        self._tick = (self._tick + 1) % 1000

        # Only show particles if there's something to drain
        if self._five_hour_pct > 0:
            while len(self._particles) < self.MAX_PARTICLES:
                self._particles.append(self._spawn_particle())

            half = self.ROWS // 2
            survivors = []
            for p in self._particles:
                p["row"] += p["speed"]
                if p["row"] >= self.ROWS:
                    pass  # drop it, will respawn
                else:
                    survivors.append(p)
            self._particles = survivors
        else:
            self._particles = []

        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        used = self._five_hour_pct / 100.0  # 0..1
        half = self.ROWS // 2

        top_fill_rows = round(half * (1.0 - used))
        bottom_fill_rows = round((self.ROWS - half) * used)
        bottom_fill_start = self.ROWS - bottom_fill_rows

        # Particle set (fractional rows, only in waist zone)
        particle_cells: set[tuple[int, int]] = set()
        for p in self._particles:
            particle_cells.add((int(p["row"]), int(p["col"])))

        for row in range(self.ROWS):
            start, end = self._col_range(row)
            for col in range(start, end):
                x = col * self.CELL
                y = row * self.CELL
                color = self._dot_color(
                    row, col, used, half, top_fill_rows, bottom_fill_start, particle_cells
                )
                if color is not None:
                    painter.fillRect(x, y, self.DOT, self.DOT, color)

        # Subtle frame border dots (outline-only for empty cells)
        self._draw_outline(painter, used, half, top_fill_rows, bottom_fill_start)

    def _dot_color(
        self,
        row: int,
        col: int,
        used: float,
        half: int,
        top_fill_rows: int,
        bottom_fill_start: int,
        particles: set[tuple[int, int]],
    ) -> Optional[QColor]:
        # Particle falling through waist
        if (row, col) in particles:
            return QColor(C["sand_full"]).lighter(130)

        if row < half:
            # Top half
            if row < top_fill_rows:
                # Sand remaining (cream), slightly dimmer near the drain edge
                edge_proximity = top_fill_rows - row
                if edge_proximity == 1:
                    return QColor(C["sand_full"]).darker(140)
                return QColor(C["sand_full"])
            else:
                # Empty area — draw a very faint dot to show the hourglass shape
                return QColor(C["bg_tertiary"])
        else:
            # Bottom half
            if row >= bottom_fill_start:
                # Used sand — color shifts with usage
                c = sand_color(used * 100)
                # Shimmer: top row of the pile is slightly brighter
                if row == bottom_fill_start and (self._tick // 3) % 4 == 0:
                    return c.lighter(115)
                return c
            else:
                return QColor(C["bg_tertiary"])

    def _draw_outline(
        self,
        painter: QPainter,
        used: float,
        half: int,
        top_fill_rows: int,
        bottom_fill_start: int,
    ) -> None:
        """Draw a subtle 1-dot outline around the hourglass perimeter."""
        outline_color = QColor(C["border"])
        for row in range(self.ROWS):
            start, end = self._col_range(row)
            if end <= start:
                continue
            prev_start, prev_end = self._col_range(row - 1) if row > 0 else (start, end)
            next_start, next_end = self._col_range(row + 1) if row < self.ROWS - 1 else (start, end)

            for col in (start, end - 1):
                # Only draw outline dot if nothing else is painted here
                dot_is_content = False
                if row < half:
                    dot_is_content = row < top_fill_rows
                else:
                    dot_is_content = row >= bottom_fill_start

                if not dot_is_content:
                    x = col * self.CELL
                    y = row * self.CELL
                    painter.fillRect(x, y, self.DOT, self.DOT, outline_color)
