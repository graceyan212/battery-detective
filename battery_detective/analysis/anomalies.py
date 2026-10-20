"""Rolling 15-minute threshold windows, merged only within continuous discharge."""

import math
from .discharge import discharge_runs, summarize_run


def detect_anomalies(samples, threshold=12):
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("Threshold must be a positive finite number.")
    anomalies = []
    for run in discharge_runs(samples):
        windows, left = [], 0
        for right in range(1, len(run)):
            while left + 1 < right and run[right]["timestamp"] - run[left+1]["timestamp"] >= 900:
                left += 1
            summary = summarize_run([run[left], run[right]], min_seconds=900)
            if summary["rate"] is not None and summary["rate"] >= threshold:
                if windows and left <= windows[-1][1]:
                    windows[-1][1] = right
                else:
                    windows.append([left, right])
        for left, right in windows:
            anomalies.append({**summarize_run([run[left], run[right]]), "threshold": threshold,
                              "reason": "Sustained discharge at or above the configured threshold."})
    return anomalies
