from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .theme import C, ui_font
from .. import config


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定 — Claude Hourglass")
        self.setMinimumWidth(480)
        self._build()
        self._load()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(20, 20, 20, 20)

        # --- DB group ---
        db_group = QGroupBox("データ保存")
        db_form = QFormLayout(db_group)
        db_form.setSpacing(8)

        self._db_edit = QLineEdit()
        self._db_edit.setFont(ui_font(10))
        db_browse = QPushButton("…")
        db_browse.setFixedWidth(32)
        db_browse.clicked.connect(self._browse_db)
        db_row = QHBoxLayout()
        db_row.setSpacing(4)
        db_row.addWidget(self._db_edit, 1)
        db_row.addWidget(db_browse)
        db_form.addRow("DB ファイル:", db_row)

        self._json_edit = QLineEdit()
        self._json_edit.setFont(ui_font(10))
        json_browse = QPushButton("…")
        json_browse.setFixedWidth(32)
        json_browse.clicked.connect(self._browse_json)
        json_row = QHBoxLayout()
        json_row.setSpacing(4)
        json_row.addWidget(self._json_edit, 1)
        json_row.addWidget(json_browse)
        db_form.addRow("最新JSON:", json_row)

        lay.addWidget(db_group)

        # --- App group ---
        app_group = QGroupBox("アプリ動作")
        app_form = QFormLayout(app_group)
        app_form.setSpacing(8)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(5, 3600)
        self._interval_spin.setSuffix(" 秒")
        self._interval_spin.setFont(ui_font(10))
        app_form.addRow("ポーリング間隔:", self._interval_spin)

        self._boot_check = QCheckBox("Windows 起動時に常駐を開始する")
        self._boot_check.setFont(ui_font(10))
        app_form.addRow("", self._boot_check)

        lay.addWidget(app_group)

        # --- Buttons ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        for btn in buttons.buttons():
            btn.setFont(ui_font(10))
        lay.addWidget(buttons)

    def _load(self) -> None:
        self._db_edit.setText(config.get("db_path"))
        self._json_edit.setText(config.get("latest_json_path"))
        self._interval_spin.setValue(config.get("poll_interval_sec"))
        self._boot_check.setChecked(config.get("start_on_boot"))

    def _save_and_accept(self) -> None:
        config.set("db_path", self._db_edit.text().strip())
        config.set("latest_json_path", self._json_edit.text().strip())
        config.set("poll_interval_sec", self._interval_spin.value())
        config.set("start_on_boot", self._boot_check.isChecked())
        self._apply_boot_setting()
        self.accept()

    def _apply_boot_setting(self) -> None:
        import sys, winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "ClaudeHourglass"
        exe = sys.executable
        cmd = f'"{exe}" -m claude_hourglass.main'
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE)
            if self._boot_check.isChecked():
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass  # non-critical

    def _browse_db(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "DB ファイルを選択", self._db_edit.text(),
            "SQLite (*.sqlite *.db);;すべてのファイル (*)"
        )
        if path:
            self._db_edit.setText(path)

    def _browse_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "JSON ファイルを選択", self._json_edit.text(),
            "JSON (*.json);;すべてのファイル (*)"
        )
        if path:
            self._json_edit.setText(path)
