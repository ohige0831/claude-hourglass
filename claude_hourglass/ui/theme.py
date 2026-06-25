from __future__ import annotations
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
C = {
    "bg_primary":    "#1C1814",
    "bg_secondary":  "#252019",
    "bg_tertiary":   "#2E2820",
    "bg_panel":      "#201D18",
    "border":        "#3A3028",
    "border_subtle": "#2A2520",
    "text_primary":  "#F5F0E8",
    "text_secondary":"#B8B0A0",
    "text_muted":    "#7A7268",
    "accent_orange": "#E8892A",
    "accent_amber":  "#C4782A",
    "accent_blue":   "#7BA7C2",
    "accent_blue_dim":"#4A6E85",
    "sand_full":     "#D4C8A8",   # sand remaining (top)
    "sand_used":     "#C4782A",   # sand used (bottom, low-med)
    "sand_high":     "#C44A2A",   # sand used (bottom, high)
    "success":       "#6B9E6B",
    "warning":       "#C4782A",
    "danger":        "#C44A2A",
}


def qc(key: str, alpha: int = 255) -> QColor:
    color = QColor(C[key])
    color.setAlpha(alpha)
    return color


def usage_color(pct: float) -> QColor:
    """Returns a QColor for a given usage percentage 0–100."""
    if pct < 50:
        return qc("accent_blue")
    if pct < 75:
        return qc("accent_orange")
    return qc("danger")


def sand_color(pct: float) -> QColor:
    """Bottom-half sand color that shifts amber→red as usage rises."""
    if pct < 75:
        return qc("sand_used")
    return qc("sand_high")


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
_UI_FAMILIES = ["IBM Plex Sans JP", "Noto Sans JP", "Inter", "Segoe UI", "sans-serif"]
_MONO_FAMILIES = ["JetBrains Mono", "IBM Plex Mono", "Cascadia Code", "Consolas", "monospace"]


def _first_available(families: list[str]) -> str:
    available = set(QFontDatabase.families())
    for f in families:
        if f in available:
            return f
    return families[-1]


def ui_font(size: int = 11, bold: bool = False) -> QFont:
    f = QFont(_first_available(_UI_FAMILIES), size)
    f.setBold(bold)
    return f


def mono_font(size: int = 12, bold: bool = False) -> QFont:
    f = QFont(_first_available(_MONO_FAMILIES), size)
    f.setBold(bold)
    return f


# ---------------------------------------------------------------------------
# Global stylesheet
# ---------------------------------------------------------------------------
STYLESHEET = f"""
QWidget {{
    background-color: {C['bg_primary']};
    color: {C['text_primary']};
    border: none;
    font-family: "IBM Plex Sans JP", "Noto Sans JP", "Inter", "Segoe UI", sans-serif;
    font-size: 11px;
}}

QMainWindow, QDialog {{
    background-color: {C['bg_primary']};
}}

QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {C['border']};
}}

/* --- Tabs --- */
QTabWidget::pane {{
    border: 1px solid {C['border']};
    border-radius: 3px;
    background: {C['bg_secondary']};
}}
QTabBar::tab {{
    background: {C['bg_tertiary']};
    color: {C['text_secondary']};
    padding: 6px 16px;
    border: 1px solid {C['border']};
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    margin-right: 2px;
    font-size: 11px;
}}
QTabBar::tab:selected {{
    background: {C['bg_secondary']};
    color: {C['text_primary']};
    border-bottom: 2px solid {C['accent_orange']};
}}
QTabBar::tab:hover:!selected {{
    background: {C['bg_secondary']};
    color: {C['text_primary']};
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {C['bg_tertiary']};
    color: {C['text_primary']};
    border: 1px solid {C['border']};
    border-radius: 3px;
    padding: 5px 14px;
    font-size: 11px;
}}
QPushButton:hover {{
    background-color: {C['bg_secondary']};
    border-color: {C['accent_amber']};
}}
QPushButton:pressed {{
    background-color: {C['bg_primary']};
}}
QPushButton[accent="true"] {{
    background-color: {C['accent_amber']};
    color: {C['bg_primary']};
    border: none;
    font-weight: bold;
}}
QPushButton[accent="true"]:hover {{
    background-color: {C['accent_orange']};
}}

/* --- Inputs --- */
QLineEdit, QSpinBox, QComboBox {{
    background: {C['bg_secondary']};
    color: {C['text_primary']};
    border: 1px solid {C['border']};
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 11px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {C['accent_blue']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
}}
QComboBox QAbstractItemView {{
    background: {C['bg_secondary']};
    color: {C['text_primary']};
    selection-background-color: {C['bg_tertiary']};
    border: 1px solid {C['border']};
}}

/* --- Checkboxes --- */
QCheckBox {{
    color: {C['text_primary']};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {C['border']};
    border-radius: 2px;
    background: {C['bg_secondary']};
}}
QCheckBox::indicator:checked {{
    background: {C['accent_amber']};
    border-color: {C['accent_amber']};
}}

/* --- Labels --- */
QLabel[heading="true"] {{
    font-size: 13px;
    font-weight: bold;
    color: {C['text_primary']};
}}
QLabel[muted="true"] {{
    color: {C['text_muted']};
    font-size: 10px;
}}

/* --- ScrollBars --- */
QScrollBar:vertical {{
    background: {C['bg_secondary']};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border']};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* --- Separator --- */
QSplitter::handle {{ background: {C['border']}; }}

/* --- GroupBox --- */
QGroupBox {{
    border: 1px solid {C['border']};
    border-radius: 3px;
    margin-top: 14px;
    padding: 8px;
    color: {C['text_secondary']};
    font-size: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
"""


def apply(app: QApplication) -> None:
    app.setStyleSheet(STYLESHEET)
