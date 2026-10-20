import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import math
from pathlib import Path
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

from ..analysis.anomalies import detect_anomalies
from ..analysis.investigation import investigate, validate_window
from ..reports.generator import render_report
from ..storage.database import Store


STATIC = Path(__file__).with_name("static")
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css")}


def make_server(database, port=8765):
    database = Path(database).expanduser().resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, data, status=200, content_type="application/json"):
            if content_type == "application/json":
                data = json.dumps(data, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if host not in allowed or (origin and origin != "http://"+host) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send({"error": "Access is limited to this local dashboard."}, 403)
                return
            url = urlsplit(self.path)
            if url.path in ASSETS:
                name, mime = ASSETS[url.path]
                self.send((STATIC/name).read_bytes(), content_type=mime)
                return
            if url.path not in ("/api/status", "/api/timeline", "/api/investigate"):
                self.send({"error": "Not found."}, 404)
                return
            try:
                if url.path == "/api/status":
                    if database.exists():
                        with Store(database, readonly=True) as store:
                            payload = store.status()
                    else:
                        payload = {"samples": 0, "first": None, "latest": None, "sources": [], "latest_sample": None}
                    self.send({**payload, "now": time.time(), "database": str(database)})
                    return
                params = parse_qs(url.query)
                start, end = float(params["start"][0]), float(params["end"][0])
                threshold = float(params.get("threshold", [12])[0])
                validate_window(start, end)
                if not math.isfinite(threshold) or threshold <= 0 or threshold > 100:
                    raise ValueError("Choose a threshold between 0 and 100 percentage points/hour.")
                if not database.exists():
                    self.send({"error": "No measurements yet. Start the collector, then refresh."}, 404)
                    return
                with Store(database, readonly=True) as store:
                    # Pin all queries to the same snapshot while the collector writes.
                    store.conn.execute("BEGIN")
                    if url.path == "/api/timeline":
                        rows = store.samples(start, end)
                        self.send({"start": start, "end": end, "samples": rows, "anomalies": detect_anomalies(rows, threshold)})
                    else:
                        result = investigate(store, start, end, threshold)
                        self.send({"investigation": result, "markdown": render_report(result)})
            except (ValueError, KeyError, OverflowError):
                self.send({"error": "Choose a valid window of up to 31 days and a positive discharge threshold."}, 400)
            except sqlite3.Error:
                self.send({"error": "Could not read the telemetry database. Check its path and retry."}, 503)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(database, port=8765):
    server = make_server(database, port)
    print(f"Dashboard: http://127.0.0.1:{server.server_port} (Ctrl-C stops only the dashboard)", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
