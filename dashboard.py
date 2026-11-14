from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import BOOK_DIR, DASHBOARD_HOST, DASHBOARD_PORT, EVENTS, ROOT, STATE
from generate import BOOK
from logs_util import load_state

WEB = ROOT


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_file(ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path == "/api/state":
            self._json(load_state())
            return
        if path == "/api/events":
            rows = []
            if EVENTS.is_file():
                for line in EVENTS.read_text(encoding="utf-8").splitlines()[-120:]:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
            self._json({"events": rows})
            return
        if path.startswith("/api/round/"):
            name = path.rsplit("/", 1)[-1]
            review = BOOK_DIR / "logs" / "rounds" / name / "review.json"
            if not review.is_file():
                self.send_error(404)
                return
            self._json(json.loads(review.read_text(encoding="utf-8")))
            return
        if path == "/book.md":
            self._send_file(BOOK, "text/plain; charset=utf-8")
            return
        super().do_GET()

    def _json(self, payload: object) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, path, content_type: str) -> None:
        from pathlib import Path

        path = Path(path)
        if not path.is_file():
            self.send_error(404)
            return
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    server = ThreadingHTTPServer((DASHBOARD_HOST, DASHBOARD_PORT), Handler)
    print(f"dashboard http://{DASHBOARD_HOST}:{DASHBOARD_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
