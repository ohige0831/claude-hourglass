"""
probe_official_webview.py — QtWebEngine による公式UI抽出の動作確認スクリプト。

使い方:
  python scripts/probe_official_webview.py

Claude.ai/settings/usage をロードし、使用データを抽出して標準出力に表示する。
事前にアプリを起動して webview_profile にログイン済みの Cookie を保存しておくか、
ウィンドウ内で手動ログインしてください。
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    print("[ERROR] PySide6-WebEngine がインストールされていません。")
    print("        pip install PySide6-WebEngine  でインストールしてください。")
    sys.exit(1)

from claude_hourglass.official_webview_collector import _EXTRACT_JS

USAGE_URL = "https://claude.ai/settings/usage"
PROFILE_DIR = Path.home() / ".claude_hourglass" / "webview_profile"


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Probe Official WebView")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile = QWebEngineProfile("hourglass-official-ui")
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    profile.setPersistentStoragePath(str(PROFILE_DIR))

    view = QWebEngineView()
    page = QWebEnginePage(profile, view)
    view.setPage(page)
    view.setWindowTitle("Probe — Claude.ai")
    view.resize(1100, 780)
    view.show()

    result_label = QLabel("読み込み中…")
    result_label.setWordWrap(True)

    info_win = QWidget()
    info_win.setWindowTitle("Probe Result")
    info_win.resize(600, 200)
    lay = QVBoxLayout(info_win)
    lay.addWidget(result_label)
    info_win.show()

    def on_load_finished(ok: bool) -> None:
        if not ok:
            result_label.setText("[FAIL] ページ読み込み失敗")
            return
        result_label.setText("SPA レンダリング待機中 (2秒)…")
        QTimer.singleShot(2000, run_js)

    def run_js() -> None:
        view.page().runJavaScript(_EXTRACT_JS, on_js_result)

    def on_js_result(result) -> None:
        if result is None:
            url = view.url().toString()
            if "login" in url.lower():
                msg = "[LOGIN REQUIRED] ウィンドウ内でログインしてください。"
            else:
                msg = f"[PARSE FAILED] URL: {url}"
            result_label.setText(msg)
            print(msg)
        else:
            text = json.dumps(result, ensure_ascii=False, indent=2)
            result_label.setText(text)
            print("[OK] 抽出結果:")
            print(text)

    view.loadFinished.connect(on_load_finished)
    view.load(USAGE_URL)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
