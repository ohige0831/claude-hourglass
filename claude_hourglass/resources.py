"""
Resource path resolution and hourglass icon rendering.

resource_path() handles both normal Python and PyInstaller frozen executables.
draw_hourglass() is the single drawing function used by both the static icon
generator (scripts/generate_icons.py) and the live tray icon (tray.py).
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QIcon, QPixmap

_ASSETS = Path(__file__).parent / "assets"

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resource_path(name: str) -> Path:
    """
    Return absolute path to an asset file.
    Works for normal Python and PyInstaller frozen mode (sys._MEIPASS).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / name
    return _ASSETS / name


def icon_path(size: int) -> Path:
    """Return path to icon_<size>.png"""
    return resource_path(f"icon_{size}.png")


def ico_path() -> Path:
    """Return path to icon.ico"""
    return resource_path("icon.ico")


def app_icon() -> "QIcon":
    """
    Build a QIcon from pre-generated PNG files.
    Falls back to ICO if PNGs are missing, or returns a blank icon.
    """
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon

    icon = QIcon()
    for size in (16, 32, 48, 256):
        p = icon_path(size)
        if p.exists():
            icon.addFile(str(p), QSize(size, size))

    if icon.isNull():
        ico = ico_path()
        if ico.exists():
            return QIcon(str(ico))

    return icon


# ---------------------------------------------------------------------------
# Hourglass drawing
# ---------------------------------------------------------------------------

#: Coordinate space for the icon geometry (square, any scale maps into this)
_GEO = 32.0

# Charcoal frame polygon vertices (in _GEO-space)
_FRAME_PTS = [
    (2, 1), (30, 1), (17, 14), (17, 18),
    (30, 31), (2, 31), (15, 18), (15, 14),
]

# Top interior: wide at top, narrow at bottom of top-half
_TOP_WIDE_Y  = 4.0;  _TOP_WIDE_XL  = 5.0;  _TOP_WIDE_XR  = 27.0
_TOP_NARR_Y  = 13.0; _TOP_NARR_XL  = 15.0; _TOP_NARR_XR  = 17.0

# Bottom interior: narrow at top, wide at bottom of bottom-half
_BOT_NARR_Y  = 19.0; _BOT_NARR_XL  = 15.0; _BOT_NARR_XR  = 17.0
_BOT_WIDE_Y  = 28.0; _BOT_WIDE_XL  = 5.0;  _BOT_WIDE_XR  = 27.0


def draw_hourglass(
    size: int,
    usage_pct: float = 0.0,
    bottom_hex: str = "#C4782A",
    top_hex: str = "#DDD5B8",
    frame_hex: str = "#2A2520",
    waist_hex: str = "#A05818",
    antialias: bool = True,
) -> "QPixmap":
    """
    Render the hourglass icon at *size*×*size* pixels.

    usage_pct (0–100) drives fill levels:
      - top half drains cream sand from bottom up
      - bottom half fills with *bottom_hex* from bottom up

    The two halves meet at the narrow waist (y≈13–19 in 32-unit space).
    """
    from PySide6.QtCore import Qt, QPointF, QRectF
    from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QPolygonF

    usage = max(0.0, min(100.0, usage_pct)) / 100.0

    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, antialias and size >= 24)
    p.setPen(Qt.NoPen)

    sc = size / _GEO

    def s(v: float) -> float:
        return v * sc

    def poly(*pts: tuple[float, float]) -> "QPolygonF":
        return QPolygonF([QPointF(s(x), s(y)) for x, y in pts])

    # --- Frame ---
    p.setBrush(QColor(frame_hex))
    p.drawPolygon(poly(*_FRAME_PTS))

    # --- Top cream sand (drains from the bottom of the top half upward) ---
    # fill_bottom_y = top of cream ↔ bottom of remaining sand
    top_fill = 1.0 - usage
    fill_bottom_y = _TOP_WIDE_Y + top_fill * (_TOP_NARR_Y - _TOP_WIDE_Y)
    if top_fill > 0.005:
        t = (fill_bottom_y - _TOP_WIDE_Y) / (_TOP_NARR_Y - _TOP_WIDE_Y)
        xl = _TOP_WIDE_XL + t * (_TOP_NARR_XL - _TOP_WIDE_XL)
        xr = _TOP_WIDE_XR + t * (_TOP_NARR_XR - _TOP_WIDE_XR)
        p.setBrush(QColor(top_hex))
        p.drawPolygon(poly(
            (_TOP_WIDE_XL, _TOP_WIDE_Y),
            (_TOP_WIDE_XR, _TOP_WIDE_Y),
            (xr, fill_bottom_y),
            (xl, fill_bottom_y),
        ))

    # --- Bottom amber sand (fills from the bottom upward) ---
    fill_top_y = _BOT_WIDE_Y - usage * (_BOT_WIDE_Y - _BOT_NARR_Y)
    if usage > 0.005:
        t = (fill_top_y - _BOT_NARR_Y) / (_BOT_WIDE_Y - _BOT_NARR_Y)
        xl = _BOT_NARR_XL + t * (_BOT_WIDE_XL - _BOT_NARR_XL)
        xr = _BOT_NARR_XR + t * (_BOT_WIDE_XR - _BOT_NARR_XR)
        p.setBrush(QColor(bottom_hex))
        p.drawPolygon(poly(
            (xl, fill_top_y),
            (xr, fill_top_y),
            (_BOT_WIDE_XR, _BOT_WIDE_Y),
            (_BOT_WIDE_XL, _BOT_WIDE_Y),
        ))

    # --- Waist (always visible, acts as the narrow "neck") ---
    p.setBrush(QColor(waist_hex))
    p.drawRect(QRectF(s(15), s(13), s(2), s(6)))

    # --- Grain dots at larger sizes for pixel-art feel ---
    if size >= 48:
        dot = max(1.5, size / 24.0)
        if top_fill > 0.3:
            g = QColor(top_hex)
            g.setAlpha(90)
            p.setBrush(g)
            for gx, gy in [(8, 6), (14, 6), (20, 6), (11, 9), (17, 9)]:
                if s(gy) < s(fill_bottom_y) - dot:
                    p.drawRect(QRectF(s(gx), s(gy), dot, dot))
        if usage > 0.3:
            g = QColor(bottom_hex)
            g.setAlpha(70)
            p.setBrush(g)
            for gx, gy in [(8, 24), (14, 23), (20, 24), (11, 26), (17, 26)]:
                if s(gy) > s(fill_top_y) + dot:
                    p.drawRect(QRectF(s(gx), s(gy), dot, dot))

    p.end()
    return px
