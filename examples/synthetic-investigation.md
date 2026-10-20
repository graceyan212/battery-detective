# Battery Detective investigation

Window: 2026-10-19 20:30:00 UTC to 2026-10-19 21:30:00 UTC

**Synthetic measurements: demonstration data, not activity from this Mac.**

## 1. What happened?

[B1] Lost 18.0 percentage points across 60 minutes of qualifying discharge: 18.0 percentage points/hour.

## 2. What changed?

Preceding equal-length window: 6.0 percentage points/hour. Workloads are not matched.
Mean system CPU changed by +47.2 percentage points relative to that window.
- [C1] Mean system CPU utilization was 56.6% of total CPU capacity.
- [P1] clang (PID 303) recorded 12600.0 CPU seconds; 350.0% mean CPU on a one-core scale during observed intervals.
- [P2] Safari (PID 202) recorded 900.0 CPU seconds; 25.0% mean CPU on a one-core scale during observed intervals.
- [P3] mdworker (PID 404) recorded 240.0 CPU seconds; 6.7% mean CPU on a one-core scale during observed intervals.
- [D1] During qualifying unplugged intervals, clang (PID 303) recorded 12600.0 CPU seconds; 350.0% mean CPU on a one-core scale.
- [D2] During qualifying unplugged intervals, Safari (PID 202) recorded 900.0 CPU seconds; 25.0% mean CPU on a one-core scale.
- [D3] During qualifying unplugged intervals, mdworker (PID 404) recorded 240.0 CPU seconds; 6.7% mean CPU on a one-core scale.
Foreground observations: Terminal (60 samples), Safari (1 samples).

## 3. Potential explanations

1. CPU work by clang may have contributed to drain during the qualifying unplugged intervals. This is a correlation, not an attribution of battery energy. Evidence: B1, D1. Confidence: Unconfirmed.
2. CPU work by Safari may have contributed to drain during the qualifying unplugged intervals. This is a correlation, not an attribution of battery energy. Evidence: B1, D2. Confidence: Unconfirmed.
3. CPU work by mdworker may have contributed to drain during the qualifying unplugged intervals. This is a correlation, not an attribution of battery energy. Evidence: B1, D3. Confidence: Unconfirmed.

## 4. Limitations

- Battery percentage is rounded; discharge rates are estimates of percentage points per hour, not instantaneous power.
- CPU activity is correlation, not proof of battery use. Display, GPU, network, thermal conditions, and other hardware are not attributed to applications.
- Foreground identity is sampled at each observation; app switches and processes that start and exit between samples can be missed.
- Brief power transitions between samples and clock changes indistinguishable from sleep cannot be reconstructed.
- Process CPU percentages use one logical core (and may exceed 100%); system CPU uses total machine capacity.
- The process table covers the whole selected window; contributor evidence uses only complete process intervals within qualifying unplugged discharge segments.
- The baseline is the preceding equal-length window, not a workload-matched or causal comparison.
- Up to 2 processes per sample could not be read with this user's permissions.

## 5. Suggested next experiments

- Repeat a comparable unplugged workload with clang idle, keeping screen brightness and network conditions similar, then compare at least 15 minutes of discharge.
- Collect a longer uninterrupted unplugged window and compare similar workloads before drawing conclusions.
