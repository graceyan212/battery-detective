"""Read-only web adapter for an explicitly exported recording, not a collector."""

import json
import math
from pathlib import Path
import sqlite3
import time

from ..analysis.anomalies import detect_anomalies
from ..analysis.investigation import investigate, validate_window
from ..reports.generator import render_report, stamp
from ..storage.database import Store


def create_app(root):
    from flask import Flask, Response, request, send_file

    root = Path(root).resolve()
    database = root / "data/recording.sqlite"
    recording = json.loads((root / "data/recording.json").read_text())
    validate_window(recording["start"], recording["end"])
    app = Flask(__name__, static_folder=None)

    def respond(payload, status=200):
        return Response(json.dumps(payload, allow_nan=False), status=status, content_type="application/json; charset=utf-8")

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        return response

    # Vercel serves public/ at its CDN; these routes also allow local previews.
    @app.get("/")
    @app.get("/app.js")
    @app.get("/style.css")
    def asset():
        names = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        return send_file(root / "public" / names[request.path])

    @app.get("/api/status")
    @app.get("/api/timeline")
    @app.get("/api/investigate")
    def api():
        try:
            with Store(database, readonly=True) as store:
                store.conn.execute("BEGIN")
                if request.path == "/api/status":
                    return respond({**store.status(), "now": time.time(), "mode": "snapshot",
                                    "recording": recording, "database": "Shared recording"})
                start, end = float(request.args["start"]), float(request.args["end"])
                threshold = float(request.args.get("threshold", 12))
                validate_window(start, end)
                if not math.isfinite(threshold) or not 0 < threshold <= 100:
                    raise ValueError("Invalid threshold")
                if request.path == "/api/timeline":
                    rows = store.samples(start, end)
                    return respond({"start": start, "end": end, "samples": rows,
                                    "anomalies": detect_anomalies(rows, threshold)})
                result = investigate(store, start, end, threshold)
                if not result["sample_count"]:
                    result["limitations"][0] = "No measurements in this window. Choose a period within the saved recording."
                result["limitations"].append("This is a saved recording. Only the exported interval is available; comparisons needing earlier history may be unavailable.")
                markdown = render_report(result)
                provenance = f"**Saved recording: {stamp(recording['start'])} to {stamp(recording['end'])}. This page does not monitor the viewer's device.**"
                markdown = markdown.replace("\n\n", f"\n\n{provenance}\n\n", 1)
                return respond({"investigation": result, "markdown": markdown})
        except (ValueError, KeyError, TypeError, OverflowError):
            return respond({"error": "Choose a valid window of up to 31 days and a threshold between 0 and 100 percentage points/hour."}, 400)
        except sqlite3.Error:
            return respond({"error": "Could not read this recording. Refresh to retry."}, 503)

    return app
