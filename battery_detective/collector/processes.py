"""Cumulative CPU counters, identified by PID AND process creation time."""

from dataclasses import dataclass
import psutil


@dataclass(frozen=True)
class Observation:
    pid: int
    started: float
    name: str
    cpu_total: float
    rss: int
    read_total: int | None = None
    write_total: int | None = None
    app_name: str | None = None
    bundle_id: str | None = None


def delta(current, previous):
    if current is None or previous is None or current < previous:
        return None
    return current - previous


class ProcessTracker:
    def __init__(self):
        self.previous = {}

    def update(self, observations, elapsed):
        rows = []
        for current in observations:
            key = (current.pid, current.started)
            previous = self.previous.get(key) if elapsed and elapsed > 0 else None
            cpu = delta(current.cpu_total, previous.cpu_total) if previous else None
            rows.append({
                "pid": current.pid, "started": current.started, "name": current.name,
                "app_name": current.app_name, "bundle_id": current.bundle_id,
                "rss": current.rss, "cpu_seconds": cpu,
                "cpu_percent": 100 * cpu / elapsed if cpu is not None else None,
                "read_bytes": delta(current.read_total, previous.read_total) if previous else None,
                "write_bytes": delta(current.write_total, previous.write_total) if previous else None,
            })
        self.previous = {(item.pid, item.started): item for item in observations}
        return rows


def read_processes(applications):
    observations, inaccessible = [], 0
    # Fresh Process objects avoid process_iter's cached identities across PID reuse.
    for pid in psutil.pids():
        try:
            process = psutil.Process(pid)
            with process.oneshot():
                started = process.create_time()
                name = process.name()
                cpu = process.cpu_times()
                rss = process.memory_info().rss
                try:
                    io = process.io_counters()
                    read, write = io.read_bytes, io.write_bytes
                except (psutil.Error, AttributeError, NotImplementedError):
                    read, write = None, None
            if psutil.Process(pid).create_time() != started:
                continue
            app = applications.get(pid, {})
            observations.append(Observation(pid, started, name, cpu.user + cpu.system, rss,
                                            read, write, app.get("name"), app.get("bundle_id")))
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except psutil.AccessDenied:
            inaccessible += 1
    return observations, inaccessible
