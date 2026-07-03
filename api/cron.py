from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json

from venue_finder.pipeline import run_once


class handler(BaseHTTPRequestHandler):  # noqa: N801
    def do_GET(self) -> None:  # noqa: N802
        inserted, csv_path, xlsx_path = run_once()
        payload = json.dumps(
            {
                "ok": True,
                "inserted": inserted,
                "csv_path": str(csv_path),
                "xlsx_path": str(xlsx_path),
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

