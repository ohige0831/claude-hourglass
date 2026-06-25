from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from .theme import C, ui_font
from .. import config
from ..resources import app_icon
from ..startup import (
    _IS_WINDOWS,
    disable_startup,
    enable_startup,
    is_startup_enabled,
    launcher_path,
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, on_open_login=None):
        super().__init__(parent)
        self._on_open_login = on_open_login
        self.setWindowTitle("設定 — Claude Hourglass")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(500)
        self._build()
        self._load()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(20, 20, 20, 20)

        # --- データ保存 ---
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

        # --- アプリ動作 ---
        app_group = QGroupBox("アプリ動作")
        app_form = QFormLayout(app_group)
        app_form.setSpacing(8)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(5, 3600)
        self._interval_spin.setSuffix(" 秒")
        self._interval_spin.setFont(ui_font(10))
        app_form.addRow("ポーリング間隔:", self._interval_spin)

        lay.addWidget(app_group)

        # --- 自動起動 ---
        startup_group = QGroupBox("自動起動")
        startup_lay = QVBoxLayout(startup_group)
        startup_lay.setSpacing(6)

        self._startup_check = QCheckBox("Windows ログオン時に Claude Hourglass を自動起動する")
        self._startup_check.setFont(ui_font(10))

        if _IS_WINDOWS:
            startup_lay.addWidget(self._startup_check)

            self._startup_info = QLabel()
            self._startup_info.setFont(ui_font(9))
            self._startup_info.setWordWrap(True)
            self._startup_info.setStyleSheet(
                f"color: {C['text_muted']}; background: transparent;"
            )
            startup_lay.addWidget(self._startup_info)
        else:
            self._startup_check.setEnabled(False)
            self._startup_check.setText(
                "Windows ログオン時に自動起動する  （Windows のみ対応）"
            )
            startup_lay.addWidget(self._startup_check)
            self._startup_info = None  # type: ignore[assignment]

        lay.addWidget(startup_group)

        # --- 公式UI連携 (WebView) ---
        wv_group = QGroupBox("公式UI連携 (WebView)")
        wv_lay = QVBoxLayout(wv_group)
        wv_lay.setSpacing(8)

        self._wv_check = QCheckBox("QtWebEngine で使用量を定期取得する")
        self._wv_check.setFont(ui_font(10))
        wv_lay.addWidget(self._wv_check)

        wv_form = QFormLayout()
        wv_form.setSpacing(6)

        self._wv_interval_spin = QSpinBox()
        self._wv_interval_spin.setRange(30, 3600)
        self._wv_interval_spin.setSuffix(" 秒")
        self._wv_interval_spin.setFont(ui_font(10))
        wv_form.addRow("取得間隔:", self._wv_interval_spin)
        wv_lay.addLayout(wv_form)

        wv_btn_row = QHBoxLayout()
        wv_btn_row.setSpacing(8)
        self._wv_login_btn = QPushButton("ログインウィンドウを開く")
        self._wv_login_btn.setFont(ui_font(10))
        self._wv_login_btn.clicked.connect(self._open_login_window)
        wv_btn_row.addWidget(self._wv_login_btn)
        wv_btn_row.addStretch()
        wv_lay.addLayout(wv_btn_row)

        self._wv_note = QLabel(
            "PySide6-WebEngine がインストールされていない場合は無効になります。\n"
            "pip install PySide6-WebEngine"
        )
        self._wv_note.setFont(ui_font(9))
        self._wv_note.setWordWrap(True)
        self._wv_note.setStyleSheet(
            f"color: {C['text_muted']}; background: transparent;"
        )
        wv_lay.addWidget(self._wv_note)

        lay.addWidget(wv_group)

        # --- ダイアログボタン ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        for btn in buttons.buttons():
            btn.setFont(ui_font(10))
        lay.addWidget(buttons)

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._db_edit.setText(config.get("db_path"))
        self._json_edit.setText(config.get("latest_json_path"))
        self._interval_spin.setValue(config.get("poll_interval_sec"))

        if _IS_WINDOWS:
            enabled = is_startup_enabled()
            self._startup_check.setChecked(enabled)
            self._update_startup_info(enabled)

        self._wv_check.setChecked(bool(config.get("official_webview_enabled")))
        self._wv_interval_spin.setValue(int(config.get("official_webview_interval_secs") or 60))

        self._wv_login_btn.setEnabled(self._on_open_login is not None)

    def _update_startup_info(self, enabled: bool) -> None:
        """ランチャーパスの案内テキストを更新する。"""
        if self._startup_info is None:
            return
        if enabled:
            vbs = launcher_path()
            self._startup_info.setText(
                f"登録済み — ランチャー: {vbs}"
            )
        else:
            self._startup_info.setText(
                "有効にすると VBS ランチャーを生成してレジストリに登録します。"
            )

    def _save_and_accept(self) -> None:
        config.set("db_path", self._db_edit.text().strip())
        config.set("latest_json_path", self._json_edit.text().strip())
        config.set("poll_interval_sec", self._interval_spin.value())
        config.set("official_webview_enabled", self._wv_check.isChecked())
        config.set("official_webview_interval_secs", self._wv_interval_spin.value())

        if _IS_WINDOWS and not self._apply_startup():
            return  # エラー発生時はダイアログを閉じない

        self.accept()

    def _apply_startup(self) -> bool:
        """
        チェックボックスの状態をレジストリに反映する。
        成功した場合は True、失敗した場合は False を返す。
        """
        want_enabled = self._startup_check.isChecked()
        currently_enabled = is_startup_enabled()

        if want_enabled == currently_enabled:
            return True  # 変更なし

        try:
            if want_enabled:
                enable_startup()
            else:
                disable_startup()
            self._update_startup_info(want_enabled)
            return True
        except OSError as e:
            QMessageBox.critical(
                self,
                "自動起動の設定に失敗しました",
                f"レジストリの更新中にエラーが発生しました。\n\n{e}",
            )
            # チェックボックスを実際の状態に戻す
            self._startup_check.setChecked(currently_enabled)
            return False

    def _open_login_window(self) -> None:
        if self._on_open_login is None:
            return
        try:
            self._on_open_login()
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "ログインウィンドウエラー", str(exc))

    # ------------------------------------------------------------------
    # File pickers
    # ------------------------------------------------------------------

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
