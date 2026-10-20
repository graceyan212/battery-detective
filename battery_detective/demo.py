"""Reproducible synthetic telemetry in a NEW database only."""

import math
import os
from pathlib import Path
import time

from .analysis.anomalies import detect_anomalies
from .storage.database import Store


def seed_demo(database, end=None):
    database = Path(database).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    end = int(time.time() if end is None else end) // 60 * 60
    start = end - 6*3600
    with Store(database) as store:
        session = store.start_session(60, "synthetic", start)
        for minute in range(361):
            if 180 < minute < 205:
                continue
            if minute <= 90:
                percent = 90 - minute/10
            elif minute <= 150:
                percent = 81 - (minute-90)*0.3
            elif minute <= 180:
                percent = 63 - (minute-150)/10
            elif minute <= 270:
                percent = 57 - (minute-205)/12
            elif minute <= 300:
                percent = 51.6 + (minute-270)*0.65
            else:
                percent = 71.1 - (minute-300)/10
            busy = 90 < minute <= 150
            plugged = 270 < minute <= 300
            gap = "first_sample" if minute == 0 else "missing_samples" if minute == 205 else None
            front = {"pid": 303 if busy else 202, "name": "Terminal" if busy else "Safari",
                     "bundle_id": "com.apple.Terminal" if busy else "com.apple.Safari"}
            cpu = (57 if busy else 10) + 4*math.sin(minute/8)
            processes = [
                {"pid": 303, "started": start-120, "name": "clang", "rss": 640_000_000,
                 "cpu_seconds": None if gap else 210 if busy else 0.2,
                 "cpu_percent": None if gap else 350 if busy else 1/3},
                {"pid": 202, "started": start-600, "name": "Safari", "app_name": "Safari",
                 "bundle_id": "com.apple.Safari", "rss": 420_000_000,
                 "cpu_seconds": None if gap else 15, "cpu_percent": None if gap else 25},
                {"pid": 404, "started": start-300, "name": "mdworker", "rss": 60_000_000,
                 "cpu_seconds": None if gap else 4, "cpu_percent": None if gap else 20/3},
            ]
            store.add_sample(session, {"timestamp": start+minute*60, "monotonic": minute*60,
                                      "elapsed_seconds": None if gap else 60, "gap_reason": gap,
                                      "battery_percent": round(percent), "plugged": plugged,
                                      "charging": plugged, "cpu_percent": None if gap else cpu,
                                      "memory_percent": 45, "observed_processes": 3,
                                      "inaccessible_processes": 2, "sensor_errors": "[]"}, processes, front)
        store.end_session(session, end)
        store.save_anomalies(start, end, detect_anomalies(store.samples(start, end)))
    return start, end
