#!/usr/bin/env python3
"""
Generate PNG icons at multiple sizes and assemble icon.ico.

Output: claude_hourglass/assets/
  icon_16.png, icon_32.png, icon_48.png, icon_256.png, icon.ico

Usage:
    python scripts/generate_icons.py
"""

from __future__ import annotations
import struct
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from PySide6.QtWidgets import QApplication

from claude_hourglass.resources import draw_hourglass

ASSETS = _ROOT / "claude_hourglass" / "assets"
SIZES = [16, 32, 48, 256]

# Static icon shows ~40% usage — cream top, amber bottom, balanced look
_ICON_USAGE_PCT = 40.0
_ICON_BOTTOM_HEX = "#C4782A"


# ---------------------------------------------------------------------------
# ICO assembler (PNG-in-ICO, supported since Windows Vista)
# ---------------------------------------------------------------------------

def _make_ico(png_paths: list[Path], output: Path) -> None:
    images: list[tuple[int, int, bytes]] = []
    for path in sorted(png_paths, key=lambda p: int(p.stem.split("_")[-1])):
        data = path.read_bytes()
        w = struct.unpack(">I", data[16:20])[0]
        h = struct.unpack(">I", data[20:24])[0]
        images.append((w, h, data))

    n = len(images)
    header = struct.pack("<HHH", 0, 1, n)  # reserved, type=ICO, count

    offset = 6 + 16 * n
    dir_bytes = b""
    for w, h, data in images:
        dir_bytes += struct.pack(
            "<BBBBHHII",
            w if w < 256 else 0,   # 0 means 256 in ICO spec
            h if h < 256 else 0,
            0,      # palette size
            0,      # reserved
            1,      # color planes
            32,     # bpp
            len(data),
            offset,
        )
        offset += len(data)

    with output.open("wb") as f:
        f.write(header)
        f.write(dir_bytes)
        for _, _, data in images:
            f.write(data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    ASSETS.mkdir(parents=True, exist_ok=True)
    png_paths: list[Path] = []

    for size in SIZES:
        px = draw_hourglass(size, usage_pct=_ICON_USAGE_PCT, bottom_hex=_ICON_BOTTOM_HEX)
        out = ASSETS / f"icon_{size}.png"
        if not px.save(str(out), "PNG"):
            print(f"  ERROR: failed to save {out}", file=sys.stderr)
            sys.exit(1)
        print(f"  {out.name}  ({size}×{size})")
        png_paths.append(out)

    ico_out = ASSETS / "icon.ico"
    _make_ico(png_paths, ico_out)
    print(f"  {ico_out.name}  ({', '.join(str(s) for s in SIZES)}px)")

    print(f"\nAll icons written to {ASSETS}")


if __name__ == "__main__":
    main()
