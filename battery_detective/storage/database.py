"""One transaction per sample, WAL readers, and no command-line histories."""

import json
import os
from pathlib import Path
import sqlite3
import time
import uuid


SAMPLE_FIELDS = (
    "timestamp monotonic elapsed_seconds battery_percent plugged charging voltage_mv "
    "current_ma cycle_count cpu_percent memory_percent gap_reason sensor_errors "
    "inaccessible_processes observed_processes duration_ms collector_cpu_seconds collector_rss"
).split()
PROCESS_FIELDS = (
    "pid started name app_name bundle_id cpu_seconds cpu_percent rss read_bytes write_bytes"
).split()


def default_database():
    return Path.home() / "Library/Application Support/Battery Detective/telemetry.sqlite"


class Store:
    def __init__(self, path, readonly=False):
        self.path = Path(path).expanduser().resolve()
        if readonly:
            self.conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        else:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            self.path.chmod(0o600)
            self.conn = sqlite3.connect(self.path, timeout=5)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.conn.close()
            raise ValueError(f"Unsupported database version {version}; upgrade Battery Detective.")
        if not readonly:
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.conn.executescript(Path(__file__).with_name("schema.sql").read_text())
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                if sidecar.exists():
                    sidecar.chmod(0o600)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.conn.close()

    def start_session(self, interval=60, source="live", timestamp=None):
        session = str(uuid.uuid4())
        with self.conn:
            self.conn.execute("INSERT INTO sessions VALUES (?, ?, NULL, ?, ?)",
                              (session, time.time() if timestamp is None else timestamp, interval, source))
        return session

    def end_session(self, session, timestamp=None):
        with self.conn:
            self.conn.execute("UPDATE sessions SET ended=? WHERE id=?",
                              (time.time() if timestamp is None else timestamp, session))

    def add_sample(self, session, sample, processes, foreground):
        with self.conn:
            fields = ["session_id", *SAMPLE_FIELDS]
            placeholders = ",".join("?" for _ in fields)
            row = self.conn.execute(
                f"INSERT INTO samples ({','.join(fields)}) VALUES ({placeholders})",
                [session, *(sample.get(key) for key in SAMPLE_FIELDS)],
            )
            sample_id = row.lastrowid
            fields = ["sample_id", *PROCESS_FIELDS]
            placeholders = ",".join("?" for _ in fields)
            self.conn.executemany(
                f"INSERT INTO process_activity ({','.join(fields)}) VALUES ({placeholders})",
                ([sample_id, *(process.get(key) for key in PROCESS_FIELDS)] for process in processes),
            )
            self.conn.execute("INSERT INTO foreground_activity VALUES (?, ?, ?, ?)",
                              (sample_id, foreground.get("pid"), foreground.get("name"), foreground.get("bundle_id")))
        return sample_id

    def samples(self, start, end):
        return [dict(row) for row in self.conn.execute(
            """SELECT s.*, f.name AS foreground_name, f.bundle_id AS foreground_bundle_id,
                      f.pid AS foreground_pid, t.source, t.interval_seconds
               FROM samples s JOIN sessions t ON t.id=s.session_id
               LEFT JOIN foreground_activity f ON f.sample_id=s.id
               WHERE s.timestamp BETWEEN ? AND ? ORDER BY s.timestamp, s.id""", (start, end))]

    def top_processes(self, start, end, limit=20):
        return [dict(row) for row in self.conn.execute(
            """SELECT p.pid, p.started, p.name, p.app_name, p.bundle_id, s.session_id,
                      SUM(p.cpu_seconds) AS cpu_seconds,
                      100.0*SUM(p.cpu_seconds)/SUM(s.elapsed_seconds) AS cpu_percent,
                      SUM(s.elapsed_seconds) AS observed_seconds,
                      MAX(p.cpu_percent) AS peak_cpu_percent, MAX(p.rss) AS peak_rss,
                      COUNT(*) AS observations,
                      SUM(CASE WHEN f.pid IS NOT NULL AND f.pid != p.pid THEN 1 ELSE 0 END) AS background_observations
               FROM samples s JOIN process_activity p ON p.sample_id=s.id
               LEFT JOIN foreground_activity f ON f.sample_id=s.id
               WHERE s.timestamp > ? AND s.timestamp <= ?
                 AND s.timestamp-s.elapsed_seconds >= ?-0.001
                 AND s.gap_reason IS NULL AND p.cpu_seconds IS NOT NULL
               GROUP BY s.session_id, p.pid, p.started, p.name, p.app_name, p.bundle_id
               ORDER BY cpu_seconds DESC LIMIT ?""", (start, end, start, limit))]

    def status(self):
        own_snapshot = not self.conn.in_transaction
        if own_snapshot:
            self.conn.execute("BEGIN")
        try:
            result = dict(self.conn.execute(
                "SELECT COUNT(*) AS samples, MIN(timestamp) AS first, MAX(timestamp) AS latest FROM samples").fetchone())
            result["sources"] = [row[0] for row in self.conn.execute("SELECT DISTINCT source FROM sessions")]
            result["latest_sample"] = self.samples(result["latest"], result["latest"])[-1] if result["latest"] is not None else None
            return result
        finally:
            if own_snapshot:
                self.conn.rollback()

    def save_anomalies(self, start, end, anomalies, threshold=12):
        with self.conn:
            self.conn.execute("DELETE FROM anomalies WHERE end >= ? AND start <= ?", (start, end))
            self.conn.executemany("INSERT INTO anomalies(start,end,threshold,details) VALUES (?,?,?,?)",
                                  [(a["start"], a["end"], threshold, json.dumps(a)) for a in anomalies])

    def prune(self, before):
        with self.conn:
            count = self.conn.execute("DELETE FROM samples WHERE timestamp < ?", (before,)).rowcount
            self.conn.execute("DELETE FROM anomalies WHERE end < ?", (before,))
            self.conn.execute("DELETE FROM sessions WHERE ended < ? AND id NOT IN (SELECT session_id FROM samples)", (before,))
        return count
