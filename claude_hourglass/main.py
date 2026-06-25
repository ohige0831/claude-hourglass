from __future__ import annotations
import sys

from PySide6.QtWidgets import QApplication

from . import config, database
from .official_webview_collector import (
    _HAS_WEBENGINE, make_collector, open_login_standalone,
)
from .receiver import start_receiver
from .resources import app_icon
from .ui import theme
from .ui.hourglass_panel import HourglassPanel
from .ui.main_window import MainWindow
from .ui.settings_dialog import SettingsDialog
from .tray import TrayManager


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Claude Hourglass")
    app.setApplicationVersion("0.1.0")

    config.load()
    theme.apply(app)
    app.setWindowIcon(app_icon())

    # Init DB
    db = config.db_path()
    database.init(db)

    # Start local HTTP receiver (background daemon thread)
    if config.get("receiver_enabled"):
        start_receiver(
            port=config.get("receiver_port"),
            official_ui_path=config.official_ui_path(),
            statusline_raw_path=config.statusline_raw_path(),
            latest_path=config.latest_json_path(),
            alt_max_age_secs=config.get("alt_max_age_secs"),
        )

    # Create WebView collector if enabled
    collector = None
    if config.get("official_webview_enabled"):
        collector = make_collector(
            profile_dir=config.webview_profile_dir(),
            usage_url=config.get("official_usage_url"),
            official_ui_path=config.official_ui_path(),
            statusline_raw_path=config.statusline_raw_path(),
            latest_path=config.latest_json_path(),
            status_path=config.webview_status_path(),
            interval_secs=config.get("official_webview_interval_secs"),
            alt_max_age_secs=config.get("alt_max_age_secs"),
        )
        collector.start()

    # Create UI components
    panel = HourglassPanel()

    # settings callback defined ahead so MainWindow can reference it immediately
    _tray_holder: list = [None]

    # GC 防止: スタンドアロンログインウィンドウの参照
    _login_wins: list = []

    def open_login() -> None:
        from PySide6.QtWidgets import QMessageBox
        if collector is not None:
            collector.open_login_window(main_win)
            return
        if not _HAS_WEBENGINE:
            QMessageBox.information(
                main_win,
                "WebEngine 未インストール",
                "公式UI WebView 連携を使用するには:\n\n"
                "  pip install PySide6-WebEngine\n\n"
                "をインストールしてください。",
            )
            return
        try:
            win = open_login_standalone(
                config.webview_profile_dir(),
                config.get("official_usage_url"),
                main_win,
            )
            if win:
                _login_wins.append(win)
        except Exception as exc:
            QMessageBox.warning(main_win, "ログインエラー", str(exc))

    def open_settings():
        dlg = SettingsDialog(main_win, on_open_login=open_login)
        if dlg.exec() and _tray_holder[0]:
            _tray_holder[0].reload_poll_interval()

    main_win = MainWindow(on_settings=open_settings, on_open_login=open_login)

    # Wire webview status path so CurrentStatusTab can poll it
    if main_win._current_tab is not None:
        main_win._current_tab.set_webview_status_path(config.webview_status_path())

    def open_main():
        main_win.refresh_charts()
        main_win.show()
        main_win.raise_()
        main_win.activateWindow()

    tray = TrayManager(
        app,
        on_open_main=open_main,
        on_open_settings=open_settings,
    )
    _tray_holder[0] = tray
    tray.set_panel(panel)

    if config.get("show_startup_panel"):
        tray.show_startup_panel()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
