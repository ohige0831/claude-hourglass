"""
official_webview_collector.py — QtWebEngine ベースの公式UI使用データ収集。

runJavaScript の戻り値型:
  JS 側で JSON.stringify() して Python 側で json.loads() する方式に統一。
  PySide6 のバージョンによって str/dict/None が返るため全パターンに対応する。

webview_status.json に記録するフィールド:
  status, enabled, url, current_url, page_title,
  inner_text_length, inner_text_head,
  headings, buttons, links, possibleUsageTexts,
  parsed, last_error, tick_count, probe_attempt, extract_attempts,
  raw_result_type, raw_result_repr, probe_json_parse_error,
  last_success_at, last_success_payload_summary,
  updated_at
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

from .official_ingest import ingest_official_usage

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_IDLE                   = "idle"
STATUS_DISABLED               = "disabled"
STATUS_CREATED                = "created"
STATUS_TICK_STARTED           = "tick_started"
STATUS_LOADING                = "loading"
STATUS_LOAD_FAILED            = "load_failed"
STATUS_PROBING                = "probing"
STATUS_PROBE_RETURNED_NONE    = "probe_returned_none"
STATUS_PROBE_TRANSPORT_FAILED = "probe_transport_failed"
STATUS_PROBE_JSON_PARSE_FAILED = "probe_json_parse_failed"
STATUS_USAGE_NOT_FOUND        = "usage_section_not_found"
STATUS_EXTRACTING             = "extracting"
STATUS_OK                     = "ok"
STATUS_LOGIN_REQUIRED         = "login_required"
STATUS_PARSE_FAILED           = "parse_failed"
STATUS_INGEST_FAILED          = "ingest_failed"
STATUS_WEBENGINE_MISSING      = "webengine_missing"

STATUS_LABELS_JA: dict[str, str] = {
    STATUS_IDLE:                    "待機中",
    STATUS_DISABLED:                "無効",
    STATUS_CREATED:                 "初期化完了",
    STATUS_TICK_STARTED:            "収集開始",
    STATUS_LOADING:                 "ページ読込中",
    STATUS_LOAD_FAILED:             "ページ読込失敗",
    STATUS_PROBING:                 "ページ確認中",
    STATUS_PROBE_RETURNED_NONE:     "プローブ応答なし",
    STATUS_PROBE_TRANSPORT_FAILED:  "プローブ転送失敗",
    STATUS_PROBE_JSON_PARSE_FAILED: "プローブJSON解析失敗",
    STATUS_USAGE_NOT_FOUND:         "使用量セクション未検出",
    STATUS_EXTRACTING:              "データ抽出中",
    STATUS_OK:                      "取得OK",
    STATUS_LOGIN_REQUIRED:          "ログインが必要です",
    STATUS_PARSE_FAILED:            "データ取得失敗",
    STATUS_INGEST_FAILED:           "保存失敗",
    STATUS_WEBENGINE_MISSING:       "WebEngine 未インストール",
}

_MAX_PROBE_ATTEMPTS   = 5
_MAX_EXTRACT_RETRIES  = 2   # extract null 後に probe を再試行できる回数
_PROBE_RETRY_MS       = 3000
_INITIAL_WAIT_MS      = 2000

# ---------------------------------------------------------------------------
# JavaScript — 診断プローブ
#
#   ok=true 条件 (いずれか満たす):
#     1. /現在のセッション|週次制限|使用済み|リセット/ が bodyText に存在
#     2. /\d+\s*%\s*(使用済み|used)/i が存在
#     3. /reset|リセット/i と /\d+\s*%/ が両方存在
#     4. "Pro" と "% 使用済み" が両方存在
#
#   Loading 検出:
#     - "Loading" が3回以上かつ上記条件を満たさない → reason="usage_panel_loading"
#     - サイドバー「使用量」だけ見えていて上記条件を満たさない → reason="usage_nav_visible_but_panel_not_ready"
#
#   戻り値: 必ず JSON.stringify(object)。絶対に null を返さない。
# ---------------------------------------------------------------------------

_PROBE_JS = r"""
(function () {
  var bodyText = (document.body && document.body.innerText) ? document.body.innerText : "";

  function makeResult(extra) {
    var headings = [];
    try {
      var hEls = document.querySelectorAll("h1,h2,h3");
      for (var i = 0; i < Math.min(hEls.length, 20); i++) {
        var t = (hEls[i].innerText || hEls[i].textContent || "").trim();
        if (t) headings.push(t);
      }
    } catch(e) {}

    var buttons = [];
    try {
      var bEls = document.querySelectorAll("button");
      for (var i = 0; i < Math.min(bEls.length, 30); i++) {
        var t = (bEls[i].innerText || bEls[i].textContent || "").trim().slice(0, 60);
        if (t) buttons.push(t);
      }
    } catch(e) {}

    var links = [];
    try {
      var aEls = document.querySelectorAll("a");
      for (var i = 0; i < Math.min(aEls.length, 30); i++) {
        var aText = (aEls[i].innerText || aEls[i].textContent || "").trim().slice(0, 40);
        links.push({ text: aText, href: aEls[i].href || "" });
      }
    } catch(e) {}

    var possibleUsageTexts = [];
    try {
      /* リーフ要素から使用量関連テキストを抽出 */
      var allEls = document.querySelectorAll("span,p,div,td,li,label,dd,dt");
      for (var i = 0; i < allEls.length && possibleUsageTexts.length < 30; i++) {
        if (allEls[i].querySelector("span,p,div,td,li,label,dd,dt")) continue; /* 非リーフはスキップ */
        var t = (allEls[i].innerText || allEls[i].textContent || "").trim();
        if (t.length > 2 && t.length < 200 &&
            /usage|limit|reset|%|使用|制限|リセット|loading|plan|message/i.test(t)) {
          possibleUsageTexts.push(t);
        }
      }
    } catch(e) {}

    return Object.assign({
      ok: false,
      reason: "",
      href: (typeof location !== "undefined") ? location.href : "",
      title: document.title || "",
      readyState: document.readyState || "",
      bodyTextLength: bodyText.length,
      bodyTextHead: bodyText.slice(0, 500),
      headings: headings,
      buttons: buttons,
      links: links,
      possibleUsageTexts: possibleUsageTexts
    }, extra || {});
  }

  try {
    /* --- readyState / body チェック --- */
    if (!document.body) {
      return JSON.stringify(makeResult({ ok: false, reason: "no_document_body" }));
    }
    if (!bodyText.trim()) {
      return JSON.stringify(makeResult({ ok: false, reason: "body_text_empty" }));
    }
    if (document.readyState !== "complete") {
      return JSON.stringify(makeResult({ ok: false, reason: "page_not_complete_readyState_" + document.readyState }));
    }

    /* --- Loading 状態検出 --- */
    var loadingCount = (bodyText.match(/\bLoading\b/gi) || []).length;

    /* --- 厳格な ok 判定 --- */
    /* 条件1: 日本語の使用量パネルキーワード */
    var cond1 = /現在のセッション|週次制限|使用済み|リセット/.test(bodyText);
    /* 条件2: "42% used" / "42% 使用済み" スタイル */
    var cond2 = /\d+\s*%\s*(使用済み|used)/i.test(bodyText);
    /* 条件3: リセット文言 + パーセント値が両方存在 */
    var cond3 = /reset|リセット/i.test(bodyText) && /\d+\s*%/.test(bodyText);
    /* 条件4: "Pro" + "% 使用済み" が両方存在 */
    var cond4 = /Pro/.test(bodyText) && /\d+\s*%\s*使用済み/.test(bodyText);

    var hasUsagePanel = cond1 || cond2 || cond3 || cond4;

    if (loadingCount >= 3 && !hasUsagePanel) {
      return JSON.stringify(makeResult({
        ok: false,
        reason: "usage_panel_loading (Loading×" + loadingCount + ")"
      }));
    }

    if (!hasUsagePanel) {
      /* サイドバーの「使用量」ナビだけ見えていてパネル未ロード */
      return JSON.stringify(makeResult({
        ok: false,
        reason: "usage_nav_visible_but_panel_not_ready"
      }));
    }

    return JSON.stringify(makeResult({ ok: true, reason: "usage_panel_data_found" }));

  } catch (e) {
    return JSON.stringify({
      ok: false,
      reason: "probe_exception: " + String(e),
      href: (typeof location !== "undefined") ? location.href : "",
      title: (typeof document !== "undefined") ? document.title : "",
      readyState: (typeof document !== "undefined") ? document.readyState : "",
      bodyTextLength: -1,
      bodyTextHead: "",
      headings: [],
      buttons: [],
      links: [],
      possibleUsageTexts: []
    });
  }
})();
"""

# ---------------------------------------------------------------------------
# JavaScript — 使用データ抽出 (probe.ok == true のときだけ実行)
#   戻り値: JSON.stringify(object) の文字列、または null。
# ---------------------------------------------------------------------------

_EXTRACT_JS = r"""
(function() {
  function getLines() {
    return (document.body.innerText || '')
      .split('\n').map(function(l){return l.trim();}).filter(function(l){return l.length > 0;});
  }
  function findSection(lines, keywords) {
    for (var i = 0; i < lines.length; i++) {
      var lower = lines[i].toLowerCase();
      if (keywords.some(function(kw){return lower.indexOf(kw.toLowerCase()) !== -1;})) return i;
    }
    return -1;
  }
  function extractPercent(lines, startIdx, windowSize) {
    windowSize = windowSize || 15;
    for (var i = startIdx; i < Math.min(startIdx + windowSize, lines.length); i++) {
      var m = lines[i].match(/(\d+(?:\.\d+)?)\s*%/);
      if (m) return parseFloat(m[1]);
    }
    return null;
  }
  function findResetLine(lines, startIdx, windowSize) {
    windowSize = windowSize || 15;
    for (var i = startIdx; i < Math.min(startIdx + windowSize, lines.length); i++) {
      if (/reset|リセット/i.test(lines[i])) return lines[i];
    }
    return null;
  }
  function durationToTimestamp(text) {
    if (!text) return null;
    if (/たった今|リセット済み|just\s*now/i.test(text))
      return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
    var ms = 0;
    var jaDays  = text.match(/(\d+)\s*日/);
    var jaHours = text.match(/(\d+)\s*時間/);
    var jaMins  = text.match(/(\d+)\s*分/);
    var enDays  = text.match(/(\d+)\s*day/i);
    var enHours = text.match(/(\d+)\s*hour/i);
    var enMins  = text.match(/(\d+)\s*min/i);
    if (jaDays)  ms += parseInt(jaDays[1])  * 86400000;
    if (jaHours) ms += parseInt(jaHours[1]) *  3600000;
    if (jaMins)  ms += parseInt(jaMins[1])  *    60000;
    if (enDays)  ms += parseInt(enDays[1])  * 86400000;
    if (enHours) ms += parseInt(enHours[1]) *  3600000;
    if (enMins)  ms += parseInt(enMins[1])  *    60000;
    if (ms === 0) return null;
    return new Date(Date.now() + ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
  }

  var lines = getLines();
  var sessionIdx   = findSection(lines, ['current session', '現在のセッション', '5-hour', 'session limit']);
  var allModelsIdx = findSection(lines, ['all models', 'すべてのモデル', '7-day', 'weekly']);

  var fiveHourPct = sessionIdx   >= 0 ? extractPercent(lines, sessionIdx)   : null;
  var sevenDayPct = allModelsIdx >= 0 ? extractPercent(lines, allModelsIdx) : null;

  if (fiveHourPct === null && sevenDayPct === null) return null;

  var fiveHourResetLine = sessionIdx   >= 0 ? findResetLine(lines, sessionIdx)   : null;
  var sevenDayResetLine = allModelsIdx >= 0 ? findResetLine(lines, allModelsIdx) : null;

  var rateLimits = {};
  if (fiveHourPct !== null) {
    rateLimits.five_hour = {
      used_percentage: fiveHourPct,
      resets_at: durationToTimestamp(fiveHourResetLine)
    };
  }
  if (sevenDayPct !== null) {
    rateLimits.seven_day = {
      used_percentage: sevenDayPct,
      resets_at: durationToTimestamp(sevenDayResetLine)
    };
  }
  return Object.keys(rateLimits).length > 0 ? JSON.stringify({rate_limits: rateLimits}) : null;
})();
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_login_standalone(profile_dir: Path, usage_url: str, parent=None):
    """
    コレクターなしでログインウィンドウを開く。
    GC 防止のため返り値を呼び出し側で保持すること。
    """
    if not _HAS_WEBENGINE:
        return None
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from .ui.official_login_window import OfficialLoginWindow
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile = QWebEngineProfile("hourglass-official-ui")
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    profile.setPersistentStoragePath(str(profile_dir))
    win = OfficialLoginWindow(profile, usage_url, parent)
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def read_webview_status(status_path: Path) -> dict:
    """ステータスファイルを読み込む。存在しなければ idle を返す。"""
    try:
        if status_path.exists():
            return json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"status": STATUS_IDLE, "updated_at": None}


# ---------------------------------------------------------------------------
# Real collector (requires QtWebEngine)
# ---------------------------------------------------------------------------

if _HAS_WEBENGINE:
    class OfficialWebViewCollector(QObject):
        """公式UI使用データを QtWebEngine で定期収集する。"""

        status_changed = Signal(str)

        def __init__(
            self,
            profile_dir: Path,
            usage_url: str,
            official_ui_path: Path,
            statusline_raw_path: Path,
            latest_path: Path,
            status_path: Path,
            interval_secs: int = 60,
            alt_max_age_secs: int = 600,
            parent: Optional[QObject] = None,
        ):
            super().__init__(parent)
            self._profile_dir         = profile_dir
            self._usage_url           = usage_url
            self._official_ui_path    = official_ui_path
            self._statusline_raw_path = statusline_raw_path
            self._latest_path         = latest_path
            self._status_path         = status_path
            self._interval_secs       = interval_secs
            self._alt_max_age_secs    = alt_max_age_secs
            self._loading             = False
            self._login_window        = None
            self._tick_count          = 0
            self._probe_attempt       = 0
            self._extract_attempts    = 0   # tick 内で extract null 後に probe を再試行した回数

            self._state: dict = {
                "status":                   STATUS_CREATED,
                "enabled":                  True,
                "url":                      usage_url,
                "current_url":              "",
                "page_title":               "",
                "inner_text_length":        None,
                "inner_text_head":          "",
                "headings":                 [],
                "buttons":                  [],
                "links":                    [],
                "possibleUsageTexts":       [],
                "parsed":                   False,
                "last_error":               "",
                "tick_count":               0,
                "probe_attempt":            0,
                "extract_attempts":         0,
                "raw_result_type":          "",
                "raw_result_repr":          "",
                "probe_json_parse_error":   "",
                "last_success_at":          None,
                "last_success_payload_summary": None,
                "updated_at":               _now_iso(),
            }

            profile_dir.mkdir(parents=True, exist_ok=True)
            self._profile = QWebEngineProfile("hourglass-official-ui")
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.ForcePersistentCookies
            )
            self._profile.setPersistentStoragePath(str(profile_dir))

            self._view = QWebEngineView()
            self._view.hide()
            page = QWebEnginePage(self._profile, self._view)
            self._view.setPage(page)
            self._view.loadFinished.connect(self._on_load_finished)

            self._timer = QTimer(self)
            self._timer.setInterval(interval_secs * 1000)
            self._timer.timeout.connect(self._collect)

            self._flush()

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def start(self) -> None:
            self._collect()
            self._timer.start()

        def stop(self) -> None:
            self._timer.stop()

        def get_status(self) -> str:
            return self._state["status"]

        # ------------------------------------------------------------------
        # Collection pipeline
        # ------------------------------------------------------------------

        def _collect(self) -> None:
            if self._loading:
                return
            self._tick_count      += 1
            self._probe_attempt    = 0
            self._extract_attempts = 0
            self._loading          = True
            self._patch(
                status=STATUS_TICK_STARTED,
                tick_count=self._tick_count,
                probe_attempt=0,
                extract_attempts=0,
                parsed=False,
                last_error="",
                current_url="",
                page_title="",
                inner_text_length=None,
                inner_text_head="",
                headings=[],
                buttons=[],
                links=[],
                possibleUsageTexts=[],
                raw_result_type="",
                raw_result_repr="",
                probe_json_parse_error="",
            )
            try:
                self._view.load(self._usage_url)  # type: ignore[arg-type]
                self._patch(status=STATUS_LOADING)
            except Exception as exc:
                self._loading = False
                self._patch(status=STATUS_LOAD_FAILED, last_error=f"load() raised: {exc}")

        def _on_load_finished(self, ok: bool) -> None:
            self._loading = False
            current_url = self._view.url().toString()
            self._patch(current_url=current_url)

            if not ok:
                self._patch(
                    status=STATUS_LOAD_FAILED,
                    last_error="loadFinished(ok=False)",
                )
                return

            self._patch(status=STATUS_PROBING)
            QTimer.singleShot(_INITIAL_WAIT_MS, self._run_probe_cycle)

        # ------------------------------------------------------------------
        # Probe-then-extract cycle (リトライあり)
        # ------------------------------------------------------------------

        def _run_probe_cycle(self) -> None:
            self._probe_attempt += 1
            self._patch(probe_attempt=self._probe_attempt)
            try:
                self._view.page().runJavaScript(_PROBE_JS, self._on_probe_result)
            except Exception as exc:
                self._patch(
                    status=STATUS_PARSE_FAILED,
                    last_error=f"runJavaScript(probe) raised: {exc}",
                )

        def _on_probe_result(self, result) -> None:
            """
            _PROBE_JS は JSON.stringify(object) を返すため result は str のはず。
            PySide6 の挙動差異で dict/None が来る場合も想定して全パターン対応。
            """
            try:
                raw_type = type(result).__name__
                raw_repr = (str(result)[:500] if result is not None else "None")
                self._patch(
                    raw_result_type=raw_type,
                    raw_result_repr=raw_repr,
                    probe_json_parse_error="",
                )

                probe_data: Optional[dict] = None
                transport_failed = False

                if result is None:
                    self._patch(
                        status=STATUS_PROBE_RETURNED_NONE,
                        last_error="runJavaScript returned None",
                    )
                    transport_failed = True

                elif isinstance(result, str):
                    stripped = result.strip()
                    if not stripped:
                        self._patch(
                            status=STATUS_PROBE_TRANSPORT_FAILED,
                            last_error="runJavaScript returned empty string",
                        )
                        transport_failed = True
                    else:
                        try:
                            probe_data = json.loads(stripped)
                        except json.JSONDecodeError as exc:
                            self._patch(
                                status=STATUS_PROBE_JSON_PARSE_FAILED,
                                probe_json_parse_error=str(exc),
                                last_error=(
                                    f"JSON.parse failed: {exc}  "
                                    f"raw={stripped[:120]}"
                                ),
                            )
                            transport_failed = True

                elif isinstance(result, dict):
                    probe_data = result  # PySide6 が自動変換した場合の互換

                else:
                    self._patch(
                        status=STATUS_PROBE_TRANSPORT_FAILED,
                        last_error=f"unexpected probe result type: {raw_type}",
                    )
                    transport_failed = True

                # -----------------------------------------------------------
                # 診断フィールドを更新して ok 判定
                # -----------------------------------------------------------
                if probe_data is not None:
                    self._patch(
                        page_title=probe_data.get("title", ""),
                        inner_text_length=probe_data.get("bodyTextLength"),
                        inner_text_head=probe_data.get("bodyTextHead", ""),
                        current_url=probe_data.get("href") or self._state["current_url"],
                        headings=[h[:80] for h in probe_data.get("headings", [])],
                        buttons=probe_data.get("buttons", []),
                        links=[
                            {**lnk, "href": lnk.get("href", "")[:120]}
                            for lnk in probe_data.get("links", [])
                        ],
                        possibleUsageTexts=probe_data.get("possibleUsageTexts", []),
                    )

                    if probe_data.get("ok"):
                        self._patch(status=STATUS_EXTRACTING)
                        try:
                            self._view.page().runJavaScript(
                                _EXTRACT_JS, self._on_js_result
                            )
                        except Exception as exc:
                            self._patch(
                                status=STATUS_PARSE_FAILED,
                                last_error=f"runJavaScript(extract) raised: {exc}",
                            )
                        return  # リトライしない

                    reason   = probe_data.get("reason", "")
                    last_err = (
                        f"attempt {self._probe_attempt}/{_MAX_PROBE_ATTEMPTS}: {reason}"
                    )
                else:
                    last_err = self._state.get("last_error", "")

                # -----------------------------------------------------------
                # リトライ or 最終失敗
                # -----------------------------------------------------------
                if self._probe_attempt < _MAX_PROBE_ATTEMPTS:
                    if probe_data is not None:
                        self._patch(status=STATUS_USAGE_NOT_FOUND, last_error=last_err)
                    else:
                        self._patch(last_error=last_err)
                    QTimer.singleShot(_PROBE_RETRY_MS, self._run_probe_cycle)
                else:
                    self._patch(
                        status=STATUS_PARSE_FAILED,
                        last_error=(
                            f"max retries ({_MAX_PROBE_ATTEMPTS}) exceeded: {last_err}"
                        ),
                    )

            except Exception as exc:
                self._patch(
                    status=STATUS_PARSE_FAILED,
                    last_error=f"_on_probe_result raised: {exc}",
                )

        def _on_js_result(self, result) -> None:
            """_EXTRACT_JS の結果を処理する。result は JSON 文字列または null。"""
            try:
                if not result:
                    url = self._state.get("current_url", "").lower()
                    if "login" in url:
                        self._patch(
                            status=STATUS_LOGIN_REQUIRED,
                            last_error="redirected to login page",
                        )
                        return

                    # Loading が残っているなら probe を再試行する
                    inner_text = self._state.get("inner_text_head", "")
                    loading_count = inner_text.lower().count("loading") if inner_text else 0
                    if (
                        loading_count >= 3
                        and self._extract_attempts < _MAX_EXTRACT_RETRIES
                    ):
                        self._extract_attempts += 1
                        self._probe_attempt = 0   # probe カウントをリセット
                        self._patch(
                            status=STATUS_USAGE_NOT_FOUND,
                            extract_attempts=self._extract_attempts,
                            last_error=(
                                f"extract null + Loading×{loading_count}, "
                                f"restarting probe (extract_attempt="
                                f"{self._extract_attempts}/{_MAX_EXTRACT_RETRIES})"
                            ),
                        )
                        QTimer.singleShot(_PROBE_RETRY_MS, self._run_probe_cycle)
                    else:
                        self._patch(
                            status=STATUS_PARSE_FAILED,
                            last_error=(
                                "EXTRACT_JS returned null "
                                "(probe said ok but extract found no data)"
                            ),
                        )
                    return

                data = json.loads(result) if isinstance(result, str) else result
                if not data.get("rate_limits"):
                    self._patch(
                        status=STATUS_PARSE_FAILED,
                        last_error=f"no rate_limits in result: {str(data)[:200]}",
                    )
                    return

                self._patch(parsed=True)

                try:
                    ingest_official_usage(
                        data,
                        self._official_ui_path,
                        self._statusline_raw_path,
                        self._latest_path,
                        alt_max_age_secs=self._alt_max_age_secs,
                        source_detail="webview",
                    )
                    # 成功時: last_success_* を更新
                    rl = data.get("rate_limits", {})
                    summary = {
                        "five_hour_pct": (
                            (rl.get("five_hour") or {}).get("used_percentage")
                        ),
                        "seven_day_pct": (
                            (rl.get("seven_day") or {}).get("used_percentage")
                        ),
                    }
                    self._patch(
                        status=STATUS_OK,
                        last_error="",
                        last_success_at=_now_iso(),
                        last_success_payload_summary=summary,
                    )
                except Exception as exc:
                    self._patch(
                        status=STATUS_INGEST_FAILED,
                        last_error=f"ingest_official_usage raised: {exc}",
                    )

            except Exception as exc:
                self._patch(
                    status=STATUS_PARSE_FAILED,
                    last_error=f"_on_js_result raised: {exc}",
                )

        # ------------------------------------------------------------------
        # State management
        # ------------------------------------------------------------------

        def _patch(self, **kwargs) -> None:
            self._state.update(kwargs)
            self._state["updated_at"] = _now_iso()
            self.status_changed.emit(self._state["status"])
            self._flush()

        def _flush(self) -> None:
            try:
                self._status_path.parent.mkdir(parents=True, exist_ok=True)
                self._status_path.write_text(
                    json.dumps(self._state, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Login window
        # ------------------------------------------------------------------

        def open_login_window(self, parent_widget=None) -> None:
            from .ui.official_login_window import OfficialLoginWindow
            if self._login_window is None or not self._login_window.isVisible():
                self._login_window = OfficialLoginWindow(
                    self._profile, self._usage_url, parent_widget
                )
                self._login_window.login_done.connect(self._on_login_done)
            self._login_window.show()
            self._login_window.raise_()
            self._login_window.activateWindow()

        def _on_login_done(self) -> None:
            if self._login_window:
                self._login_window.hide()
            self._collect()


# ---------------------------------------------------------------------------
# Null fallback (no QtWebEngine)
# ---------------------------------------------------------------------------

class NullCollector(QObject):
    """QtWebEngine が利用できない場合のスタブ。"""

    status_changed = Signal(str)

    def __init__(
        self,
        status_path: Optional[Path] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._status_path = status_path
        if status_path:
            self._write_missing()

    def _write_missing(self) -> None:
        try:
            self._status_path.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
            self._status_path.write_text(  # type: ignore[union-attr]
                json.dumps({
                    "status":     STATUS_WEBENGINE_MISSING,
                    "enabled":    False,
                    "last_error": "PySide6-WebEngine not installed",
                    "updated_at": _now_iso(),
                }, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def get_status(self) -> str:
        return STATUS_WEBENGINE_MISSING

    def open_login_window(self, parent_widget=None) -> None:
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_collector(
    profile_dir: Path,
    usage_url: str,
    official_ui_path: Path,
    statusline_raw_path: Path,
    latest_path: Path,
    status_path: Path,
    interval_secs: int = 60,
    alt_max_age_secs: int = 600,
    parent: Optional[QObject] = None,
):
    if not _HAS_WEBENGINE:
        return NullCollector(status_path=status_path, parent=parent)
    return OfficialWebViewCollector(
        profile_dir=profile_dir,
        usage_url=usage_url,
        official_ui_path=official_ui_path,
        statusline_raw_path=statusline_raw_path,
        latest_path=latest_path,
        status_path=status_path,
        interval_secs=interval_secs,
        alt_max_age_secs=alt_max_age_secs,
        parent=parent,
    )
