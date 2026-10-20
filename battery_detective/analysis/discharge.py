"""Percentage-point rates, deliberately conservative about discontinuities."""


def continuity_issue(left, right):
    dt = right["timestamp"] - left["timestamp"]
    if left.get("session_id") != right.get("session_id"):
        return "session_boundary"
    if right.get("gap_reason"):
        return right["gap_reason"]
    if dt <= 0:
        return "clock_change"
    if dt > right.get("interval_seconds", 60) * 1.5:
        return "missing_samples"
    elapsed = right.get("elapsed_seconds")
    if elapsed is None or abs(dt - elapsed) > 2:
        return "unknown_interval"
    if left.get("monotonic") is not None and right.get("monotonic") is not None:
        if abs(dt - (right["monotonic"] - left["monotonic"])) > 2:
            return "sleep_or_clock_change"
    return None


def discharge_runs(samples):
    runs, current = [], []
    for left, right in zip(samples, samples[1:]):
        valid = (not continuity_issue(left, right)
                 and left.get("plugged") == 0 and right.get("plugged") == 0
                 and not left.get("charging") and not right.get("charging")
                 and left.get("battery_percent") is not None and right.get("battery_percent") is not None
                 and 0 <= right["battery_percent"] <= left["battery_percent"] <= 100)
        if valid:
            if not current:
                current = [left]
            current.append(right)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def summarize_run(run, min_seconds=600, min_loss=2):
    first, last = run[0], run[-1]
    duration = last["timestamp"] - first["timestamp"]
    loss = first["battery_percent"] - last["battery_percent"]
    return {"start": first["timestamp"], "end": last["timestamp"],
            "start_percent": first["battery_percent"], "end_percent": last["battery_percent"],
            "duration_seconds": duration, "loss": loss,
            "rate": loss * 3600 / duration if duration >= min_seconds and loss >= min_loss else None}


def discharge_segments(samples):
    return [summarize_run(run) for run in discharge_runs(samples)]


def discharge_summary(samples):
    segments = discharge_segments(samples)
    meaningful = [segment for segment in segments if segment["rate"] is not None]
    duration = sum(segment["duration_seconds"] for segment in meaningful)
    loss = sum(segment["loss"] for segment in meaningful)
    return {"rate": loss * 3600 / duration if duration else None, "loss": loss,
            "duration_seconds": duration, "segments": segments,
            "valid_discharge_seconds": sum(segment["duration_seconds"] for segment in segments),
            "excluded_short_segments": len(segments) - len(meaningful)}
