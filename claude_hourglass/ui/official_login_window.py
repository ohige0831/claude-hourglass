"""
official_login_window.py — Claude.ai ログイン用 WebView ウィンドウ。

OfficialWebViewCollector と同じプロファイルを使うため、
ここでログインした Cookie は収集用の非表示 View にも引き継がれる。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

from .theme import C, ui_font
from ..resources import app_icon


class OfficialLoginWindow(QWidget):
    """Claude.ai をブラウザ表示してユーザーにログインさせるウィンドウ。"""

    login_done = Signal()

    def __init__(
        self,
        profile: "QWebEngineProfile",
        usage_url: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Claude Hourglass — Claude.ai ログイン")
        self.setWindowIcon(app_icon())
        self.resize(1000, 720)
        self._usage_url = usage_url

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"background: {C['bg_secondary']}; border-bottom: 1px solid {C['border']};"
        )
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(16, 0, 16, 0)
        bar_lay.setSpacing(12)

        hint = QLabel(
            "Claude.ai にログインしてください。ログイン完了後に「ログイン完了」を押してください。"
        )
        hint.setFont(ui_font(10))
        hint.setStyleSheet(f"color: {C['text_primary']}; background: transparent;")
        bar_lay.addWidget(hint, 1)

        done_btn = QPushButton("ログイン完了")
        done_btn.setFont(ui_font(10))
        done_btn.clicked.connect(self.login_done)
        bar_lay.addWidget(done_btn)

        root.addWidget(bar)

        if _HAS_WEBENGINE:
            self._view = QWebEngineView()
            page = QWebEnginePage(profile, self._view)
            self._view.setPage(page)
            self._view.load("https://claude.ai")
            root.addWidget(self._view, 1)
        else:
            msg = QLabel("PySide6-WebEngine がインストールされていません。")
            msg.setFont(ui_font(12))
            msg.setStyleSheet(
                f"color: {C['text_muted']}; background: {C['bg_primary']};"
            )
            root.addWidget(msg, 1)
