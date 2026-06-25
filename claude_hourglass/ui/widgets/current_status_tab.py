from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ..theme import C, mono_font, ui_font
from .hourglass_widget import HourglassWidget
from ...models import UsageSnapshot
from ...official_webview_collector import STATUS_LABELS_JA, read_webview_status
from ...sources import SOURCE_LABELS_JA


class _LargeHourglassWidget(HourglassWidget):
    """Scale-up of HourglassWidget for the main window (6px dots)."""
    DOT = 6
    GAP = 1
    CELL = DOT + GAP  # 7px/cell → 154×252px


class _Card(QWidget):
    """Stat card with title heading and labeled value rows."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self.setStyleSheet(
            "QWidget#stat_card {"
            f"  background: {C['bg_tertiary']};"
            f"  border: 1px solid {C['border']};"
            "  border-radius: 6px;"
            "}"
        )
        self.setMinimumWidth(280)
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(12, 7, 12, 7)
        self._inner.setSpacing(4)

        heading = QLabel(title)
        heading.setFont(ui_font(9))
        heading.setStyleSheet(f"color: {C['text_muted']}; background: transparent; border: none;")
        self._inner.addWidget(heading)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C['border_subtle']}; border: none;")
        self._inner.addWidget(sep)

    def add_row(self, label: str, font_size: int = 11) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label)
        lbl.setFont(ui_font(9))
        lbl.setStyleSheet(f"color: {C['text_muted']}; background: transparent; border: none;")
        lbl.setFixedWidth(76)
        val = QLabel("—")
        val.setFont(mono_font(font_size))
        val.setStyleSheet(f"color: {C['text_primary']}; background: transparent; border: none;")
        val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        val.setMinimumWidth(60)
        row.addWidget(lbl)
        row.addWidget(val, 1)
        self._inner.addLayout(row)
        return val


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct_color(p: float) -> str:
    if p >= 75:
        return C["danger"]
    if p >= 50:
        return C["accent_orange"]
    return C["text_primary"]


_MAX_RESET_SECS = 8 * 24 * 3600  # Claude の制限窓はこれより長くならない


def _fmt_countdown(resets_at: Optional[str]) -> str:
    """'Xh Ym' remaining, or 'リセット済み'. null や異常値は '—'."""
    if not resets_at:
        return "—"
    try:
        dt = _parse_utc(resets_at)
        if dt is None:
            return "—"
        secs = int((dt - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "リセット済み"
        if secs > _MAX_RESET_SECS:  # エポック0由来の巨大値を除外
            return "—"
        h, rem = divmod(secs, 3600)
        return f"{h}h {rem // 60:02d}m"
    except Exception:
        return "—"


def _fmt_local_time(resets_at: Optional[str]) -> str:
    """Local JST time string 'MM/DD HH:MM'. null や異常値は '—'."""
    if not resets_at:
        return "—"
    try:
        dt = _parse_utc(resets_at)
        if dt is None:
            return "—"
        secs = (dt - datetime.now(timezone.utc)).total_seconds()
        # 8日超の未来 or 7日超の過去 (epoch 0 ゴミ値など) は表示しない
        if secs > _MAX_RESET_SECS or secs < -7 * 24 * 3600:
            return "—"
        return dt.astimezone().strftime("%m/%d %H:%M")
    except Exception:
        return "—"


def _parse_utc(ts) -> Optional[datetime]:
    """ISO 文字列またはエポック秒 (int/float) を UTC datetime に変換する。"""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(str(ts), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class CurrentStatusTab(QWidget):
    """「現在」タブ — 大きな砂時計 + 現在の使用状況カード。"""

    def __init__(self, on_refresh=None, on_open_login=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._on_refresh = on_refresh
        self._on_open_login = on_open_login
        self._webview_status_path: Optional[object] = None
        self._build()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        content = QHBoxLayout()
        content.setSpacing(20)

        # ---- Left: large hourglass ----
        self._hourglass = _LargeHourglassWidget(self)
        content.addWidget(self._hourglass, 0, Qt.AlignTop)

        # ---- Right: stat cards in a container widget with minimum width ----
        right_container = QWidget()
        right_container.setMinimumWidth(340)
        right_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right = QVBoxLayout(right_container)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)

        # 5時間制限
        card5 = _Card("5時間制限")
        self._v5_pct = card5.add_row("使用率", 14)
        self._v5_countdown = card5.add_row("リセットまで", 11)
        self._v5_time = card5.add_row("リセット時刻", 11)
        right.addWidget(card5)

        # 7日制限
        card7 = _Card("7日制限")
        self._v7_pct = card7.add_row("使用率", 14)
        self._v7_countdown = card7.add_row("リセットまで", 11)
        self._v7_time = card7.add_row("リセット時刻", 11)
        right.addWidget(card7)

        # その他
        card_other = _Card("その他")
        self._v_cost = card_other.add_row("累計コスト", 11)
        self._v_model = card_other.add_row("モデル", 10)
        self._v_model.setWordWrap(True)
        self._v_source = card_other.add_row("ソース", 10)
        self._v_source.setWordWrap(True)
        self._v_updated = card_other.add_row("最終更新", 10)
        right.addWidget(card_other)

        # 公式UI連携
        card_webview = _Card("公式UI連携 (WebView)")
        self._v_wv_status = card_webview.add_row("状態", 10)
        self._v_wv_updated = card_webview.add_row("最終取得", 10)
        wv_btn_row = QHBoxLayout()
        self._login_btn = QPushButton("ログインを開く")
        self._login_btn.setFont(ui_font(9))
        self._login_btn.setVisible(False)
        self._login_btn.clicked.connect(self._do_open_login)
        wv_btn_row.addStretch()
        wv_btn_row.addWidget(self._login_btn)
        card_webview._inner.addLayout(wv_btn_row)
        right.addWidget(card_webview)

        right.addStretch()

        content.addWidget(right_container, 1)
        root.addLayout(content, 1)

    # ------------------------------------------------------------------

    def _do_refresh(self) -> None:
        if self._on_refresh:
            self._on_refresh()

    def _do_open_login(self) -> None:
        if self._on_open_login:
            self._on_open_login()

    def set_webview_status_path(self, path) -> None:
        """ステータスファイルのパスを設定する (main.py から呼ぶ)。"""
        self._webview_status_path = path

    def update_webview_status(self) -> None:
        """ステータスファイルを読み取って UI を更新する。"""
        if self._webview_status_path is None:
            return
        info = read_webview_status(Path(str(self._webview_status_path)))
        status = info.get("status", "idle")
        label = STATUS_LABELS_JA.get(status, status)
        self._v_wv_status.setText(label)

        updated = info.get("updated_at")
        if updated:
            try:
                dt = _parse_utc(updated)
                self._v_wv_updated.setText(dt.astimezone().strftime("%H:%M:%S") if dt else updated)
            except Exception:
                self._v_wv_updated.setText(updated)
        else:
            self._v_wv_updated.setText("—")

        self._login_btn.setVisible(status == "login_required")

    def update_snapshot(self, snap: Optional[UsageSnapshot]) -> None:
        if snap is None:
            self._hourglass.set_usage(0.0, 0.0)
            return

        h5 = snap.effective_five_hour_pct
        h7 = snap.effective_seven_day_pct
        self._hourglass.set_usage(h5, h7)

        # 5時間制限
        pct5_text = f"{h5:.1f}%"
        if snap.five_hour_expired:
            pct5_text += "  （リセット済み）"
        self._v5_pct.setText(pct5_text)
        self._v5_pct.setStyleSheet(
            f"color: {_pct_color(h5)}; background: transparent; border: none;"
            f" font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: bold;"
        )
        self._v5_countdown.setText(_fmt_countdown(snap.five_hour_resets_at))
        self._v5_time.setText(_fmt_local_time(snap.five_hour_resets_at))

        # 7日制限
        pct7_text = f"{h7:.1f}%"
        if snap.seven_day_expired:
            pct7_text += "  （リセット済み）"
        self._v7_pct.setText(pct7_text)
        self._v7_pct.setStyleSheet(
            f"color: {_pct_color(h7)}; background: transparent; border: none;"
            f" font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: bold;"
        )
        self._v7_countdown.setText(_fmt_countdown(snap.seven_day_resets_at))
        self._v7_time.setText(_fmt_local_time(snap.seven_day_resets_at))

        # その他
        if snap.total_cost_usd is not None:
            self._v_cost.setText(f"${snap.total_cost_usd:.4f}")
        else:
            self._v_cost.setText("—")

        self._v_model.setText(snap.model_display_name or "—")

        # ソース表示 (差異があれば alt 値も併記)
        src_ja = SOURCE_LABELS_JA.get(snap.source or "", snap.source_label or "—")
        source_text = src_ja
        if snap.alt_source and snap.alt_five_hour_pct is not None:
            diff = abs((snap.alt_five_hour_pct or 0.0) - snap.effective_five_hour_pct)
            if diff >= 2.0:
                alt_ja = SOURCE_LABELS_JA.get(snap.alt_source, snap.alt_source_label or snap.alt_source)
                source_text += f"  (alt {alt_ja}: {snap.alt_five_hour_pct:.1f}%)"
        self._v_source.setText(source_text)

        try:
            dt = _parse_utc(snap.captured_at)
            if dt:
                self._v_updated.setText(dt.astimezone().strftime("%H:%M:%S"))
            else:
                self._v_updated.setText(snap.captured_at)
        except Exception:
            self._v_updated.setText(snap.captured_at or "—")

        self.update_webview_status()
