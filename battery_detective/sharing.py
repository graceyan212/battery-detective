"""Prepare an explicit interval for sharing, without copying the live database."""

import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

from .analysis.investigation import validate_window
from .storage.database import Store


PACKAGE = Path(__file__).parent
RUNTIME_FILES = (
    "__init__.py", "analysis/__init__.py", "analysis/discharge.py",
    "analysis/anomalies.py", "analysis/investigation.py",
    "storage/__init__.py", "storage/database.py",
    "reports/__init__.py", "reports/generator.py",
    "dashboard/__init__.py", "dashboard/hosted.py",
)
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}


def export_recording(database, output, start, end):
    """Create a standalone deployment in a new directory; never upload it here."""
    validate_window(start, end)
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise FileExistsError("Choose a new output directory; existing files will not be replaced.")
    with Store(database, readonly=True) as source:
        # Read a consistent WAL snapshot while the original recorder keeps writing.
        source.conn.execute("BEGIN")
        count = source.conn.execute("SELECT COUNT(*) FROM samples WHERE timestamp BETWEEN ? AND ?", (start, end)).fetchone()[0]
        if not count:
            raise ValueError("No recorded measurements in that interval. Choose a recorded time range.")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".battery-share-", dir=output.parent) as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            snapshot = root / "data/recording.sqlite"
            destination = sqlite3.connect(snapshot)
            try:
                destination.execute("PRAGMA foreign_keys=ON")
                destination.executescript((PACKAGE / "storage/schema.sql").read_text())
                queries = {
                    "sessions": "SELECT * FROM sessions WHERE id IN (SELECT session_id FROM samples WHERE timestamp BETWEEN ? AND ?)",
                    "samples": "SELECT * FROM samples WHERE timestamp BETWEEN ? AND ?",
                    "process_activity": "SELECT p.* FROM process_activity p JOIN samples s ON s.id=p.sample_id WHERE s.timestamp BETWEEN ? AND ?",
                    "foreground_activity": "SELECT f.* FROM foreground_activity f JOIN samples s ON s.id=f.sample_id WHERE s.timestamp BETWEEN ? AND ?",
                }
                with destination:
                    for table, query in queries.items():
                        cursor = source.conn.execute(query, (start, end))
                        placeholders = ",".join("?" for _ in cursor.description)
                        destination.executemany(f"INSERT INTO {table} VALUES ({placeholders})", cursor)
                    # A reading inside the export can summarize activity before it.
                    # Keep its instantaneous values, but discard partial intervals.
                    destination.execute(
                        """UPDATE process_activity SET cpu_seconds=NULL, cpu_percent=NULL,
                                  read_bytes=NULL, write_bytes=NULL
                           WHERE sample_id IN (SELECT id FROM samples
                                               WHERE timestamp-elapsed_seconds < ?)""", (start,))
                    destination.execute(
                        "UPDATE samples SET cpu_percent=NULL, elapsed_seconds=NULL WHERE timestamp-elapsed_seconds < ?",
                        (start,))
                    # The exported sessions end with the recording, not a live writer.
                    destination.execute("UPDATE sessions SET started=MAX(started, ?), ended=MIN(COALESCE(ended, ?), ?)", (start, end, end))
                destination.execute("PRAGMA journal_mode=DELETE")
            finally:
                destination.close()
            snapshot.chmod(0o600)
            metadata = {"version": 1, "start": start, "end": end, "samples": count}
            (root / "data/recording.json").write_text(json.dumps(metadata, indent=2) + "\n")

            # Explicit allowlist: no collector, full history, attachments, or secrets.
            for name in RUNTIME_FILES:
                target = root / "battery_detective" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PACKAGE / name, target)
            (root / "public").mkdir()
            for name in ("index.html", "app.js", "style.css"):
                shutil.copyfile(PACKAGE / "dashboard/static" / name, root / "public" / name)
            (root / "app.py").write_text("from pathlib import Path\nfrom battery_detective.dashboard.hosted import create_app\n\napp = create_app(Path(__file__).parent)\n")
            (root / "requirements.txt").write_text("Flask>=3.1,<4\n")
            (root / ".python-version").write_text("3.12\n")
            (root / ".vercelignore").write_text(".vercel/\n.git/\n.env*\n__pycache__/\n**/__pycache__/\n*.pyc\n")
            config = {"$schema": "https://openapi.vercel.sh/vercel.json", "framework": "flask",
                      "functions": {"app.py": {"maxDuration": 30}},
                      "headers": [{"source": "/(.*)", "headers": [{"key": key, "value": value} for key, value in SECURITY_HEADERS.items()]}]}
            (root / "vercel.json").write_text(json.dumps(config, indent=2) + "\n")
            root.rename(output)
    return output
