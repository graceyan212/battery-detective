# Battery Detective — Engineering Brief

## Project Overview

Build **Battery Detective**, a lightweight, local-first macOS battery monitoring and investigation tool that continuously collects battery and system activity data, identifies periods of unusually high battery drain, and helps users understand what was happening on their computer during those periods.

The central question the product should answer is:

**"Why did my MacBook battery drain so quickly between 1 PM and 4 PM?"**

Rather than simply displaying battery statistics, Battery Detective should correlate battery discharge with application activity, CPU utilization, background processes, and other available system telemetry to produce useful, evidence-backed explanations.

The project is also intended as an exploration of macOS systems programming, performance monitoring, observability, and software quality engineering.

## Project Goals

1. Continuously collect system and battery telemetry with minimal overhead.
2. Store historical measurements locally so users can investigate earlier activity.
3. Detect time periods with unusually high battery drain.
4. Correlate abnormal drain with relevant system and application activity.
5. Generate concise, evidence-grounded investigation reports.
6. Make the collector reliable, efficient, and transparent about measurement limitations.

**The priority is correctness and engineering quality over visual polish.**

## Reference Project

Study the open-source project:

https://github.com/MuratDugan/openmacbattery

Pay particular attention to:

- `Sampler.swift` — periodic collection and cumulative counter deltas.
- `BundleResolver.swift` — mapping processes to applications.
- `Database.swift` — efficient SQLite storage of time-series data.

Use the repository as an architectural reference, but implement our own application. Do not copy large portions of its source code.

Important lessons from OpenMacBattery include process identity using PID plus start time, lightweight periodic sampling, handling inaccessible processes, and distinguishing relative process-energy counters from total battery consumption.

---

## Technical Architecture

Use the following stack for the MVP:

| Component | Technology |
|---|---|
| Data collector | Python 3 |
| System/process monitoring | `psutil` |
| macOS-specific information | Native macOS APIs through PyObjC or small Swift helper |
| Database | SQLite |
| Analysis | Python, NumPy/Pandas if useful |
| Dashboard | Streamlit or lightweight local web app |
| AI explanations | Optional LLM integration |
| Background execution | macOS `launchd` LaunchAgent |
| Testing | pytest |

Favor a modular architecture so the collector, analysis engine, and UI can evolve independently.

Suggested project structure:

```text
battery-detective/
├── collector/
│   ├── battery.py
│   ├── processes.py
│   ├── foreground.py
│   └── sampler.py
├── analysis/
│   ├── discharge.py
│   ├── anomalies.py
│   └── investigation.py
├── storage/
│   ├── database.py
│   └── schema.sql
├── dashboard/
│   └── app.py
├── reports/
│   └── generator.py
├── tests/
├── scripts/
│   └── install_agent.sh
├── requirements.txt
└── README.md
```

This structure is a suggestion, not a requirement. Prefer simplicity over unnecessary abstraction.

---

## Phase 1 — Continuous Telemetry Collection

Build a Python process that samples system activity every 30–60 seconds.

### Data to collect

**Battery telemetry**
- Timestamp.
- Battery percentage.
- Charging/discharging status.
- Whether the device is connected to external power.
- Available battery/power measurements exposed by macOS.

**System telemetry**
- Overall CPU utilization.
- CPU activity per process.
- Process name and PID.
- Process start time, to distinguish reused PIDs.
- Memory usage.
- Available process I/O counters, when useful.

**Application context**
- Foreground application name.
- Foreground application bundle identifier.
- Running background processes.
- Optional high-level workload labels.

Use `NSWorkspace.frontmostApplication` for foreground application context if practical.

Do not collect keystrokes, screenshots, document contents, browser history, or other unnecessary personal information.

### Sampling requirements

- Default to one sample every 60 seconds.
- Ensure samples have accurate timestamps.
- Reuse previous process observations when calculating interval-based utilization.
- Handle processes that exit between samples.
- Handle inaccessible system processes gracefully.
- Avoid treating a reused PID as the same process.
- Avoid recording impossible negative resource deltas.
- Handle sleep, wake, missing samples, and charging transitions.
- Keep the collector's own CPU and memory use low.

Do not require administrator privileges for the basic collector.

Detailed measurements requiring elevated permissions, such as certain `powermetrics` samplers, should be optional and not necessary for the MVP.

### Storage

Store samples in SQLite.

Design tables for:
- Battery/system samples.
- Process activity.
- Foreground application activity.
- Sampling sessions.
- Detected anomalies.

Use appropriate indexes for timestamp-based queries.

Avoid writing one database transaction for every individual process.

Implement basic retention and pruning if practical.

**Deliverable:** A collector that can run continuously for several hours and store useful historical data.

---

## Phase 2 — Battery Timeline Dashboard

Build a clean, minimal dashboard for exploring historical battery activity.

The UI should have three main sections.

### A. Battery timeline

Display:
- Battery percentage over time.
- Charging periods.
- Discharging periods.
- Missing measurements.
- Periods of unusually fast discharge.

Allow users to select different time windows, such as the last hour, last six hours, today, or a custom range.

### B. System activity

Display system activity alongside the battery timeline:
- CPU utilization over time.
- Foreground application timeline.
- Processes with the highest recorded CPU activity.
- Background processes associated with unusual activity.

Avoid implying that CPU usage directly equals battery energy consumption.

### C. Investigation panel

Users should be able to select a suspicious period and ask:

"Why was my battery draining so quickly here?"

Display measurements and correlated activity for that time window.

Use a clean, technical aesthetic inspired by modern developer tools rather than a consumer wellness dashboard.

Keep the UI restrained and information-dense.

---

## Phase 3 — Battery Drain Analysis

Implement deterministic logic for analyzing battery discharge.

### Discharge rate

For a valid discharging interval:

`discharge_rate = battery_percentage_lost / elapsed_hours`

For example, a drop from 80% to 70% over one hour corresponds to 10 percentage points per hour.

Important constraints:
- Do not include charging intervals.
- Do not bridge sleep periods or missing data.
- Avoid calculating meaningful rates from tiny percentage changes over very short intervals.
- Recognize that reported battery percentage is quantized and not a precise instantaneous power measurement.

### Anomaly detection

Initially use straightforward statistical approaches:
- Rolling averages.
- Comparison with similar historical workloads.
- Configurable thresholds.
- Minimum-duration requirements.

Do not introduce ML models unless they produce demonstrably better results.

### Investigation analysis

For an anomalous period, calculate:
- Battery change and estimated discharge rate.
- Comparison with an appropriate baseline.
- Processes with elevated CPU activity.
- Foreground application history.
- Relevant changes in system activity.
- Data quality issues and missing observations.

Separate observations from causal hypotheses.

**Deliverable:** A structured investigation object containing measurements, suspected contributors, evidence, and uncertainty.

---

## Phase 4 — AI-Assisted Investigation

Add an optional LLM layer that converts the structured investigation data into a readable report.

The LLM should not calculate battery discharge rates or invent measurements.

Instead, provide it with verified results from the analysis engine.

### Report format

Each report should include:

**1. What happened?**

A concise description of the battery drain and relevant time window.

**2. What changed?**

Measured differences in CPU utilization, process activity, or other available metrics.

**3. Potential explanations**

Ranked hypotheses supported by specific observations.

**4. Limitations**

What the available data cannot establish.

**5. Suggested next experiments**

Actions a user could take to test the hypotheses under comparable conditions.

### AI reliability requirements

- Never fabricate process activity or telemetry.
- Distinguish correlations from causes.
- Reference underlying observations.
- Explicitly communicate uncertainty.
- Work without an API key by falling back to a deterministic report.
- Do not send raw activity histories to an external model without explicit user approval.

---

## Phase 5 — Background Execution

Create a macOS LaunchAgent so the collector can start automatically when the user logs in.

Requirements:
- User-level execution, without root privileges.
- Start/stop/status commands.
- Logging for collector errors.
- Graceful shutdown.
- No duplicate collector instances.
- Recovery from ordinary process crashes.
- No unnecessary polling while the system is asleep.

The dashboard should be independently launchable. Closing the dashboard must not stop telemetry collection.

The background agent must be opt-in, with a clear uninstall procedure.

---

## Phase 6 — Testing and Validation

This project is about quality engineering, so the monitoring software must itself be reliable.

Implement tests for:

- Discharge-rate calculations.
- Charging/discharging transitions.
- Sleep and missing-data gaps.
- PID reuse.
- Process termination.
- Database writes and queries.
- Anomaly detection.
- Investigation report generation.

Create synthetic test datasets with known patterns, including periods of high CPU usage and rapid battery drain.

Make sure the detector identifies meaningful anomalies without flagging every ordinary variation.

### Collector overhead

Measure the collector's own CPU utilization, memory usage, and sampling duration.

Where feasible, compare baseline activity with the collector enabled and disabled.

Document any measurable monitoring overhead.

A battery-monitoring tool should not significantly worsen the battery consumption it is measuring.

---

## MVP Acceptance Criteria

The MVP is complete when:

- [ ] The collector runs on an Apple Silicon MacBook without root access.
- [ ] Battery and process activity are recorded automatically.
- [ ] Data is stored persistently in SQLite.
- [ ] The dashboard displays a historical battery timeline.
- [ ] The user can select a time window for investigation.
- [ ] The program calculates discharge rates correctly for valid intervals.
- [ ] The program identifies potentially unusual drain periods.
- [ ] The investigation report identifies relevant measured activity.
- [ ] The program explicitly distinguishes measured facts from hypotheses.
- [ ] Tests cover major edge cases.
- [ ] The README includes setup, usage, architecture, and limitations.

## Stretch Goals

Only implement these after the MVP works:

- LLM-powered explanations.
- Native macOS menu-bar application.
- Integration with `powermetrics`.
- Per-process macOS energy counters.
- Comparison of similar workloads across different days.
- More sophisticated historical baselines.
- Automated controlled-experiment mode.
- CSV/JSON export.
- Energy-impact calibration.
- Dockerized analysis service, if it provides a real benefit.

Do not Dockerize the macOS telemetry collector itself. It needs access to host-specific macOS APIs and processes.

---

## Development Priorities

We have a short development window, so implement in this order:

**Priority 1:** Reliable data collection and storage.

**Priority 2:** Battery timeline and meaningful investigation logic.

**Priority 3:** Tests and reliability improvements.

**Priority 4:** AI explanation and UI polish.

Do not sacrifice correctness to add more features.

## Working Style

Before coding:

1. Inspect the development environment and confirm macOS and Python compatibility.
2. Review the OpenMacBattery repository for relevant architecture and platform constraints.
3. Produce a concise implementation plan.
4. Identify any required permissions.
5. Start implementing the smallest end-to-end working version.

As development progresses, run the actual collector, inspect real output, and verify the dashboard against stored measurements.

Document what the software actually measures versus what it estimates.

Avoid adding speculative capabilities that macOS does not expose through the selected APIs.

## Final Deliverables

Provide:

1. Working local application.
2. Automated tests.
3. Setup and startup instructions.
4. README explaining the architecture.
5. Example investigation report based on actual or clearly labeled synthetic measurements.
6. Known limitations and next steps.

The final result should demonstrate not just the ability to display battery data