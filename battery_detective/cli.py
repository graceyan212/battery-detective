import argparse
from datetime import datetime
import math
from pathlib import Path
import sqlite3
import sys
import time

from .storage.database import Store, default_database


def integer_between(low, high):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("Enter a whole number.") from None
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"Choose a value from {low} to {high}.")
        return number
    return parse


def parse_time(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Include a timezone, for example 2026-10-19T13:00:00-07:00 or a trailing Z for UTC.")
    return date.timestamp()


def build_parser():
    parser = argparse.ArgumentParser(description="Local battery telemetry and evidence-based investigations.")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="Run the foreground collector; Ctrl-C stops it")
    collect.add_argument("--interval", type=integer_between(30, 60), default=60)
    collect.add_argument("--count", type=integer_between(1, 1000000), help="Stop after this many successful samples")
    collect.add_argument("--retention-days", type=integer_between(1, 365), default=7)
    dashboard = commands.add_parser("dashboard", help="Serve the local dashboard independently")
    dashboard.add_argument("--port", type=integer_between(1024, 65535), default=8765)
    demo = commands.add_parser("demo", help="Create a new, clearly labeled synthetic database")
    report = commands.add_parser("report", help="Print a deterministic Markdown investigation")
    report.add_argument("--start", required=True, help="ISO timestamp including timezone")
    report.add_argument("--end", required=True, help="ISO timestamp including timezone")
    report.add_argument("--threshold", type=float, default=12)
    prune = commands.add_parser("prune", help="Delete samples older than the specified retention")
    prune.add_argument("--days", type=integer_between(1, 365), default=7)
    agent = commands.add_parser("agent", help="Opt-in user LaunchAgent management")
    agent.add_argument("action", choices=["install", "start", "stop", "status", "uninstall"])
    agent.add_argument("--dry-run", action="store_true", help="Print the install plist without writing or loading it")
    for command in (collect, dashboard, demo, report, prune, agent):
        command.add_argument("--db", type=Path, default=default_database(), help="SQLite file path")
    # A demo never defaults to the live history path.
    demo.set_defaults(db=Path("demo.sqlite"))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "collect":
            from .collector.runtime import run_collector
            run_collector(args.db, args.interval, args.count, args.retention_days)
        elif args.command == "dashboard":
            from .dashboard.server import serve
            serve(args.db, args.port)
        elif args.command == "demo":
            from .demo import seed_demo
            seed_demo(args.db)
            print(f"Synthetic demonstration created: {args.db.resolve()}")
        elif args.command == "agent":
            from .agent import manage_agent
            manage_agent(args.action, args.db, args.dry_run)
        elif args.command == "report":
            from .analysis.investigation import investigate
            from .reports.generator import render_report
            if not math.isfinite(args.threshold) or args.threshold <= 0:
                raise ValueError("Threshold must be a positive finite number.")
            with Store(args.db, readonly=True) as store:
                print(render_report(investigate(store, parse_time(args.start), parse_time(args.end), args.threshold)), end="")
        elif args.command == "prune":
            with Store(args.db) as store:
                print(f"Deleted {store.prune(time.time()-args.days*86400)} old samples.")
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"Battery Detective: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0
