from __future__ import annotations
import sys

from PySide6.QtWidgets import QApplication

from . import config, database
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

    # Create UI components
    panel = HourglassPanel()

    # settings callback defined ahead so MainWindow can reference it immediately
    _tray_holder: list = [None]

    def open_settings():
        dlg = SettingsDialog(main_win)
        if dlg.exec() and _tray_holder[0]:
            _tray_holder[0].reload_poll_interval()

    main_win = MainWindow(on_settings=open_settings)

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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
