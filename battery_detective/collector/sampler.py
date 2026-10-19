"""Sequential samples; wall/monotonic comparison catches sleep and clock jumps."""

import json
import time
import psutil

from .battery import read_battery
from .foreground import read_applications
from .processes import ProcessTracker, read_processes


def interval_quality(previous, current, interval):
    if previous is None:
        return None, "first_sample"
    wall, awake = current[0] - previous[0], current[1] - previous[1]
    if wall <= 0 or awake <= 0:
        return None, "clock_change"
    if abs(wall - awake) > 2:
        return None, "sleep_or_clock_change"
    if wall > interval * 1.5:
        return None, "missing_samples"
    return wall, None


def system_cpu_percent(previous, current):
    if previous is None:
        return None
    total, idle = current[0] - previous[0], current[1] - previous[1]
    if total <= 0 or idle < 0 or idle > total:
        return None
    return 100 * (total - idle) / total


class Sampler:
    def __init__(self, store, session, interval=60):
        self.store, self.session, self.interval = store, session, interval
        self.processes = ProcessTracker()
        self.previous_clock = self.previous_cpu = None

    def sample(self):
        started_cpu, started_mono = time.process_time(), time.monotonic()
        clock = (time.time(), started_mono)
        elapsed, gap = interval_quality(self.previous_clock, clock, self.interval)
        battery, errors = read_battery()
        foreground, applications, app_errors = read_applications()
        observations, inaccessible = read_processes(applications)
        cpu_times = psutil.cpu_times()
        cpu = (sum(cpu_times), cpu_times.idle)
        sample = {**battery, "timestamp": clock[0], "monotonic": clock[1],
                  "elapsed_seconds": elapsed, "gap_reason": gap,
                  "cpu_percent": system_cpu_percent(self.previous_cpu, cpu) if elapsed else None,
                  "memory_percent": psutil.virtual_memory().percent,
                  "observed_processes": len(observations), "inaccessible_processes": inaccessible,
                  "sensor_errors": json.dumps(errors + app_errors),
                  "duration_ms": (time.monotonic() - started_mono) * 1000,
                  "collector_cpu_seconds": time.process_time() - started_cpu,
                  "collector_rss": psutil.Process().memory_info().rss}
        rows = self.processes.update(observations, elapsed)
        sample_id = self.store.add_sample(self.session, sample, rows, foreground)
        self.previous_clock, self.previous_cpu = clock, cpu
        return sample_id
