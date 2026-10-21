# Battery Detective PRD

**Scope:** Minimum viable product (MVP) for Apple Silicon MacBooks.

## TL;DR

- **Problem:** A MacBook owner notices fast battery drain but cannot reconstruct what was running.
- **Product:** Record battery and app activity locally; let users select a period and inspect measurements, possible contributors, and a useful next experiment.
- **MVP:** An independent recorder, interactive dashboard, conservative drain detection, and downloadable reports. No account, administrator access, or AI key required.
- **Success:** Users can understand a battery drop and investigate a supported suspicion without mistaking CPU activity for proof of energy consumption.

## User and core experience

The initial user will investigate their own Mac and be comfortable following terminal setup instructions. The product should answer: **“Why did my battery drain so quickly between 1 PM and 4 PM?”**

1. **Record:** Start collection explicitly or opt into recording at login. Sample every 60 seconds by default, configurable from 30–60 seconds; retain seven days by default.
2. **Explore:** View aligned battery, CPU, and sampled foreground-app history. Show external power, gaps, and sustained fast drain. Support preset/custom ranges and selecting an interval on the chart.
3. **Investigate:** Show battery loss, estimated drain rate, process activity, comparison context, and possible contributors. Save a Markdown report covering what happened, what changed, possible explanations, limitations, and next experiments.

The dashboard must explain unfamiliar terms and units, show sample freshness and timezone, distinguish real from synthetic data, and handle empty/stale history and errors clearly. Recent readings must not imply guaranteed ongoing recording; failed requests must not leave misleading results available to download.

## Measurements and proposed stack

A **sample** is one set of readings; a **process** is a running program or helper; the **foreground app** is the app active when sampled.

| Evidence | Source and meaning |
| --- | --- |
| Battery and power | `psutil`, a Python system-statistics library, for percentage and adapter status; macOS `ioreg` for optional charging state, voltage, current, and cycle count. Plugged in and charging are distinct. |
| CPU and memory | `psutil` for system CPU, each process's CPU time, and working memory (RAM). Calculate CPU activity from changes between readings. Read process I/O counters only where available. |
| App context | macOS `NSWorkspace` through PyObjC, which lets Python call Mac APIs, for the foreground app and directly available app identities. |
| Data quality | Record timing, gaps, sensor failures, inaccessible processes, and the recorder's CPU, memory, and sampling duration. |

Use Python 3.11+, SQLite for local history, HTML/CSS/JavaScript served by Python for the dashboard, an optional macOS LaunchAgent for login startup, and pytest for automated checks. Keep collection, storage, analysis, reporting, and UI separate.

## Analysis and trust requirements

- **Estimate drain:** Percentage points lost ÷ elapsed hours. Require at least 10 continuous unplugged minutes and a two-point drop; 80% to 74% in 30 minutes means 12 points/hour.
- **Flag sustained fast drain:** Use rolling windows of at least 15 minutes and two points lost, with a configurable default threshold of 12 points/hour. Merged windows must still meet the threshold. A flag is a screening result, not a diagnosis.
- **Respect missing evidence:** Charging, battery increases, missing readings, sleep, clock changes, and restarts must break discharge continuity. Unknown readings must remain unknown. Identify processes by both ID and start time to avoid confusing reused IDs; do not guess helper ownership.
- **Support hypotheses:** Rank up to five possible contributors by CPU time within valid unplugged segments. Compare with the preceding equal-length window when available, while explaining that workloads may differ. Each hypothesis must cite observations and suggest a focused comparison experiment.

Process CPU at 100% means one fully busy core; multiple cores can exceed 100%. CPU activity does not measure an app's battery share. Rounded battery readings produce estimates; sampling can miss brief activity, and foreground observations are not continuous usage durations.

## Reliability, privacy, and boundaries

Collection must continue when the dashboard closes. Prevent duplicate recorders, save all readings in a sample together, allow dashboard reads while recording, recover from ordinary failures, and handle sleep without inventing readings. Provide explicit start/stop/status controls, opt-in login startup, retention, and uninstall that preserves history.

Keep history and dashboard access local. Require no elevated permissions, accounts, uploads, analytics, or external assets. Never collect keystrokes, screenshots, window titles, document contents, browser history, command-line arguments, or environment variables. Keep synthetic data separate from real recordings.

The MVP excludes exact per-app energy attribution, automatic corrective actions, battery-health diagnosis, sleep-drain explanations, cloud monitoring, and direct GPU, display, network, or thermal measurements. Correctness takes priority over polish.

## Acceptance criteria

Release requires:

- Several hours of actual unplugged recording, plus sleep/wake, charger-transition, restart, and checks of opt-in login startup and crash recovery.
- Deterministic tests for known drain rates, anomaly thresholds, missing data, process identity/counter changes, storage integrity, and report evidence.
- Browser checks confirming selections, charts, errors, and downloads agree with stored data; network checks confirming local operation.
- A user walkthrough showing that someone unfamiliar with system metrics can distinguish facts from suspicions and choose a next experiment.
- Repeated recorder-on/off trials documenting total CPU, memory, storage growth, and battery impact. Set and meet an overhead budget before broader release; do not assume negligible cost.

## Delivery and future steps

Build in order: **reliable collection → dashboard and deterministic investigation → hardware and usability validation.**

After the MVP:

1. **Optional AI explanations:** Connect an LLM (large language model) or other AI to a bounded summary of verified findings. Explain possible concerns, answer questions, and suggest experiments. Keep calculations in local code, link claims to evidence, state uncertainty, require explicit consent before external transfer, and retain useful reports when AI is unavailable. AI must not change system settings or stop processes; validate factual accuracy and usefulness before shipping.
2. **Better evidence:** Evaluate workload-matched comparisons, additional sensors, and controlled experiments. Adopt richer detection only when it improves on the deterministic baseline.
3. **Easier use and sharing:** Explore simpler setup, session exports, a shareable recorded demo, a menu-bar interface, and broader Mac compatibility.

Supporting technical context: [measurements and architecture](measurements.md). Setup and project overview: [README](../README.md).
