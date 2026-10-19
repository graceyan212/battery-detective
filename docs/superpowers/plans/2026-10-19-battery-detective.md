# Battery Detective implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Steps use checkboxes for tracking.

**Goal:** Build the local macOS battery investigation MVP described in the supplied engineering brief.

**Architecture:** A Python collector writes atomic samples to SQLite. A separate loopback HTTP dashboard reads the same database and uses the deterministic analysis engine. No remote services, API keys, or automatic background installation.

**Tech stack:** Python 3.11+, psutil, PyObjC AppKit on macOS, SQLite, standard-library HTTP server, plain HTML/CSS/JavaScript, pytest.

**Spec:** `docs/engineering-brief.md` (user-supplied).

## Global constraints

- Default to one sample every 60 seconds.
- Do not require administrator privileges for the basic collector.
- Do not collect keystrokes, screenshots, document contents, browser history, or other unnecessary personal information.
- Do not bridge sleep periods or missing data.
- Separate observations from causal hypotheses.
- The background agent must be opt-in, with a clear uninstall procedure.
- Work in the existing Conductor worktree and preserve its branch name.

## Review focus

- Clock changes and short sleeps must invalidate intervals even when timestamps are close.
- Reused PIDs, counter resets, and temporarily inaccessible processes must not invent CPU activity.
- Selected window boundaries must not include CPU or discharge from outside that window.
- Empty databases, missing batteries, unavailable AppKit, and external power must produce useful states.
- Concurrent readers, transaction failures, and collector restarts must preserve stored history.

## Decisions

- Use a lightweight local web app rather than Streamlit: no chart CDN, remote font, telemetry, or heavyweight dashboard dependency.
- Use a conservative fixed threshold initially: 12 percentage points/hour over rolling 15-minute windows with at least 2 percentage points lost. Require 10 minutes and 2 points before reporting a meaningful discharge rate. Show a descriptive prior-window baseline; do not label it a matched workload.
- Keep seven days of raw samples by default, with daily pruning. Preserve process identity and per-process CPU seconds; do not estimate per-app watts.
- Read optional charging state, voltage, current, and cycles from AppleSmartBattery via the system ioreg tool. Missing fields remain unknown. Foreground and direct running-app identities come from NSWorkspace; helper processes remain separate.
- Visual direction: technical instrument. A wide, aligned battery/CPU plot and foreground strip are the signature. Palette: paper #f6f8fa, surface #ffffff, ink #20303c, muted #657582, teal #167c80, amber #af7222. Avenir Next for interface text, Menlo for measured values. Compact controls, an activity table and an evidence panel below the chart. No decorative hero or external assets.

## Task 1: Telemetry and storage

**Files:** `battery_detective/collector/{battery,foreground,processes,sampler}.py`, `battery_detective/storage/{database.py,schema.sql}`, `tests/test_{processes,storage,sampler}.py`, package configuration.

**Interfaces:** `ProcessTracker.update(observations, elapsed) -> list[dict]`; `Store(path, readonly=False)` with `start_session`, `add_sample`, `samples`, `top_processes`, `prune`; `Sampler.sample() -> sample id`.

- [ ] Write tests for PID reuse, process disappearance, counter resets, gap detection, atomic storage, indexed window queries, and pruning.
- [ ] Run tests and observe missing behavior.
- [ ] Implement cumulative deltas, wall/monotonic continuity, nullable sensors, atomic batched writes, sessions, and restricted file permissions.
- [ ] Run `python -m pytest tests/test_processes.py tests/test_storage.py tests/test_sampler.py -q`; expect all passing.
- [ ] Commit the tested collector/storage implementation.

## Task 2: Discharge, anomalies, and reports

**Files:** `battery_detective/analysis/{discharge,anomalies,investigation}.py`, `battery_detective/reports/generator.py`, `tests/test_analysis.py`, `tests/test_reports.py`.

**Interfaces:** `discharge_segments(samples) -> list[dict]`; `detect_anomalies(samples, threshold=12) -> list[dict]`; `investigate(store, start, end) -> dict`; `render_report(investigation) -> str`.

- [ ] Write tests for stable discharge, charging transitions, quantization, sleeps, missing sensors, sessions, baseline absence, and selected-window clipping.
- [ ] Run the tests and observe missing behavior.
- [ ] Implement continuity-aware rates, rolling threshold windows, evidence-linked observations and hypotheses, and five-section deterministic reports.
- [ ] Run `python -m pytest -q`; expect all passing.
- [ ] Commit the tested analysis and reports.

## Task 3: Commands and background lifecycle

**Files:** `battery_detective/{__main__,cli,agent,demo}.py`, `battery_detective/collector/runtime.py`, `scripts/install_agent.sh`, `tests/test_runtime.py`, `tests/test_cli.py`.

**Interfaces:** `python -m battery_detective {collect,dashboard,demo,report,prune,agent}`. Collector locks canonical database path; signal handlers stop gracefully. Agent operations use a generated user plist and launchctl.

- [ ] Write tests for duplicate exclusion, restart/release, argument validation, plist paths containing spaces, and synthetic data isolation.
- [ ] Run tests and observe missing behavior.
- [ ] Implement CLI, bounded error retries, daily retention, opt-in launchctl commands, logging, and a clearly labeled deterministic demo dataset.
- [ ] Run `python -m pytest -q`; expect all passing.
- [ ] Commit the tested runtime.

## Task 4: Local dashboard

**Files:** `battery_detective/dashboard/{server.py,static/index.html,static/app.js,static/style.css}`, `tests/test_dashboard.py`.

**Interfaces:** Read-only GET `/api/timeline?start=&end=` and `/api/investigate?start=&end=`; loopback-only listener; `/api/status` for database coverage and provenance.

- [ ] Write HTTP tests for empty data, range validation, actual persisted samples, malicious origins/hosts, and read-only behavior.
- [ ] Run tests and observe missing behavior.
- [ ] Implement accessible responsive charts, preset/custom windows, interval selection, process table, and evidence/report panel.
- [ ] Run all tests and verify real and demo data in Brave, including mobile layout and empty states.
- [ ] Commit the tested dashboard.

## Task 5: Real validation and handoff

**Files:** `README.md`, `docs/validation.md`, `examples/synthetic-investigation.md`.

- [ ] Run a real non-root collector and inspect SQLite rows, process deltas, sensor limitations, and sampling overhead.
- [ ] Exercise graceful shutdown and duplicate collector exclusion; inspect generated LaunchAgent without installing it.
- [ ] Generate a synthetic report, run the full suite, compile Python files, and inspect the dashboard visually.
- [ ] Request one independent whole-branch review under the executing-plans skill, address substantive findings, and rerun affected checks.
- [ ] Document setup, startup, architecture, measurements versus estimates, overhead, limitations, and follow-up soak testing; commit final deliverables.
