"""שרת מקומי (Local Worker). ספריית סטנדרט בלבד, קושר ל-127.0.0.1 בלבד.

הפעלה (מתוך תיקיית worker):
    python3 -m app.server --seed        # טוען נתוני דמה בפעם הראשונה
    python3 -m app.server               # http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import service
from .db import connect
from .pipeline.market import freshness
from .service import ServiceError

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB_PATH = DATA / "portfolio.sqlite"
FIXTURES = DATA / "fixtures"
RAW_CACHE = DATA / "raw"
CONFIG = Path(__file__).resolve().parents[1] / "config" / "sources.json"
WEB_DIST = ROOT / "web" / "dist"
MAX_BODY = 5 * 1024 * 1024
LOCK = threading.Lock()


class Ctx:
    conn = None
    sources: list[dict] = []


def _json_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length > MAX_BODY:
        raise ServiceError("הבקשה גדולה מדי")
    if length == 0:
        return {}
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ServiceError("גוף הבקשה אינו JSON תקין") from exc


def route(method: str, path: str, query: dict, body_fn) -> tuple[int, object]:
    conn = Ctx.conn
    if method == "GET" and path == "/api/health":
        return 200, {"ok": True}
    if method == "GET" and path == "/api/catalog":
        return 200, service.catalog(conn)
    if method == "GET" and path == "/api/sources":
        return 200, freshness(conn)
    if method == "GET" and path == "/api/dashboard":
        return 200, service.dashboard(conn, query.get("product_type", ["all"])[0])
    if method == "GET" and path == "/api/holdings":
        return 200, service.list_holdings(conn, query.get("product_type", ["all"])[0])
    if method == "POST" and path == "/api/holdings":
        b = body_fn()
        return 201, service.create_holding(conn, b.get("track_key", ""), b.get("label", ""), b.get("opened_on"))

    m = re.fullmatch(r"/api/holdings/([\w-]+)/(draft|confirm|manual-statement|benchmark)", path)
    if m:
        hid, action = m.groups()
        if action == "draft" and method == "POST":
            b = body_fn()
            try:
                raw = base64.b64decode(b.get("content_base64", ""), validate=True)
            except ValueError as exc:
                raise ServiceError("תוכן הקובץ אינו Base64 תקין") from exc
            return 200, service.draft_statement(conn, b.get("filename", "upload"), raw)
        if action == "confirm" and method == "POST":
            b = body_fn()
            return 201, service.confirm_statement(conn, hid, b.get("draft", {}), b.get("edits", {}))
        if action == "manual-statement" and method == "POST":
            b = body_fn()
            return 201, service.add_manual_statement(
                conn, hid, b.get("as_of", ""), float(b.get("balance_ils", 0)), b.get("track_key", ""),
                b.get("monthly_deposit_ils"), b.get("fee_deposit_pct"), b.get("fee_accum_pct"))
        if action == "benchmark" and method == "GET":
            return 200, service.benchmark(conn, hid)

    if method == "POST" and path == "/api/whatif":
        b = body_fn()
        return 200, service.whatif(
            conn, b.get("holding_id", ""), b.get("alt_track_key", ""),
            int(b.get("window_months", 36)), int(b.get("horizon_years", 10)),
            float(b.get("fee_delta_pct", 0.0)), b.get("monthly_deposit_ils"),
        )
    if method == "POST" and path == "/api/market/import":
        b = body_fn()
        return 200, service.manual_import_csv(conn, b.get("csv", ""))
    if method == "POST" and path == "/api/market/sync":
        b = body_fn()
        return 200, service.sync_source(conn, Ctx.sources, b.get("source_id", ""), RAW_CACHE)
    m = re.fullmatch(r"/api/tracks/([\w-]+)/series", path)
    if method == "GET" and m:
        return 200, service.track_series(conn, m.group(1))
    return 404, {"error": "לא נמצא"}


class Handler(BaseHTTPRequestHandler):
    server_version = "PensionWorker/1.0"

    def log_message(self, fmt, *args):  # אין לוג של תוכן בקשות
        return

    def _send(self, status: int, payload: object, ctype="application/json; charset=utf-8") -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path: str) -> bool:
        if not WEB_DIST.exists():
            return False
        target = (WEB_DIST / path.lstrip("/")).resolve() if path != "/" else WEB_DIST / "index.html"
        if WEB_DIST.resolve() not in target.parents and target != WEB_DIST / "index.html":
            return False
        if not target.is_file():
            target = WEB_DIST / "index.html"
        ctype = {".html": "text/html", ".js": "application/javascript", ".css": "text/css",
                 ".svg": "image/svg+xml", ".woff2": "font/woff2"}.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), f"{ctype}; charset=utf-8" if ctype.startswith("text") else ctype)
        return True

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            if method == "GET" and self._static(parsed.path):
                return
            self._send(404, {"error": "לא נמצא"})
            return
        try:
            with LOCK:
                status, payload = route(method, parsed.path, parse_qs(parsed.query), lambda: _json_body(self))
            self._send(status, payload)
        except ServiceError as exc:
            self._send(400, {"error": str(exc)})
        except Exception:  # noqa: BLE001 - לא מחזירים פרטי פנים או תוכן דוחות
            self._send(500, {"error": "שגיאה פנימית. בדקו את לוג השרת המקומי"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def make_server(host: str = "127.0.0.1", port: int = 8765, db_path: Path = DB_PATH) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit("השרת מותר לקשור ל-localhost בלבד")
    Ctx.conn = connect(db_path)
    Ctx.sources = service.load_sources(Ctx.conn, CONFIG)
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--seed", action="store_true", help="טוען נתוני דמה")
    args = ap.parse_args()
    srv = make_server(port=args.port, db_path=args.db)
    if args.seed:
        print(service.seed_demo(Ctx.conn, FIXTURES))
    print(f"Local worker on http://127.0.0.1:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
