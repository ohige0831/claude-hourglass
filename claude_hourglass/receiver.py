"""
receiver.py — ブラウザ拡張からの使用データを受け取るローカル HTTP サーバー。

エンドポイント:
  POST /ingest/official-usage  → latest_official_ui.json 保存 + latest_usage.json 再構築
  GET  /health                 → {"status": "ok"}

デフォルトポート: 127.0.0.1:43871
"""

from __future__ import annotations
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

from .official_ingest import ingest_official_usage


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _make_handler(
    official_ui_path: Path,
    statusline_raw_path: Path,
    latest_path: Path,
    alt_max_age_secs: int = 600,
):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # suppress default access log

        def _send_json(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path == "/health":
                self._send_json(200, {"status": "ok"})
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/ingest/official-usage":
                self._send_json(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)

            try:
                data = json.loads(raw)
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
                return

            try:
                ingest_official_usage(
                    data, official_ui_path, statusline_raw_path, latest_path,
                    alt_max_age_secs=alt_max_age_secs,
                    source_detail="receiver",
                )
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
                return

            self._send_json(200, {"ok": True})

    return Handler


def start_receiver(
    port: int,
    official_ui_path: Path,
    statusline_raw_path: Path,
    latest_path: Path,
    alt_max_age_secs: int = 600,
) -> Optional[_ThreadingHTTPServer]:
    """
    バックグラウンドスレッドで HTTP サーバーを起動する。
    ポート競合など失敗した場合は None を返す。
    """
    try:
        handler = _make_handler(official_ui_path, statusline_raw_path, latest_path,
                                alt_max_age_secs=alt_max_age_secs)
        server = _ThreadingHTTPServer(("127.0.0.1", port), handler)
        t = threading.Thread(target=server.serve_forever, daemon=True, name="hourglass-receiver")
        t.start()
        return server
    except Exception:
        return None
