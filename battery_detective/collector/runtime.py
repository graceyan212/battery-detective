"""Single-writer collector lifecycle with interruptible waits and bounded retries."""

import fcntl
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time

from .sampler import Sampler
from ..analysis.anomalies import detect_anomalies
from ..storage.database import Store


class CollectorAlreadyRunning(RuntimeError):
    pass


class CollectorLock:
    def __init__(self, database):
        self.path = Path(str(Path(database).expanduser().resolve()) + ".lock")
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise CollectorAlreadyRunning("A collector is already running for this database.") from None
        os.ftruncate(self.fd, 0)
        os.write(self.fd, str(os.getpid()).encode())
        return self

    def __exit__(self, *args):
        # Do not unlink: another process could lock a different inode at the same path.
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def run_collector(database, interval=60, count=None, retention_days=7):
    os.umask(0o077)
    stop = threading.Event()
    old_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        with CollectorLock(database), Store(database) as store:
            if "synthetic" in store.status()["sources"]:
                raise ValueError("This is a synthetic database. Choose a separate database for live collection.")
            logger = logging.getLogger("battery_detective.collector")
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(store.path.parent / "collector.log", maxBytes=1_000_000, backupCount=3)
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            session = store.start_session(interval)
            sampler = Sampler(store, session, interval)
            successes = errors = 0
            last_prune = 0
            logger.info("Collector started; interval=%ss", interval)
            print(f"Collecting every {interval}s into {store.path}", flush=True)
            try:
                while not stop.is_set():
                    tick = time.monotonic()
                    try:
                        sample_id = sampler.sample()
                        successes += 1
                        errors = 0
                        now = time.time()
                        if now - last_prune >= 86400:
                            store.prune(now-retention_days*86400)
                            last_prune = now
                        if successes % 15 == 0:
                            rows = store.samples(now-3600, now)
                            store.save_anomalies(now-3600, now, detect_anomalies(rows))
                        logger.info("Sample %s: %.1f ms including storage", sample_id, (time.monotonic()-tick)*1000)
                    except (OSError, sqlite3.Error, RuntimeError) as exc:
                        errors += 1
                        logger.exception("Sampling failed (%s/3): %s", errors, type(exc).__name__)
                        # A failed write cannot become the baseline of the next committed interval.
                        sampler = Sampler(store, session, interval)
                        if errors >= 3:
                            raise
                    if count is not None and successes >= count:
                        break
                    # Relative sleep does not wake a sleeping Mac and never backfills missed ticks.
                    stop.wait(max(0.1, interval - (time.monotonic()-tick)))
            finally:
                store.end_session(session)
                logger.info("Collector stopped; %s samples", successes)
                logger.removeHandler(handler)
                handler.close()
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)

