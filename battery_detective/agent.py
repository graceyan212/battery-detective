"""Explicit user-level LaunchAgent operations. Importing this installs nothing."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys


LABEL = "local.battery-detective.collector"


def agent_definition(python, database, project, logs):
    return {"Label": LABEL,
            "ProgramArguments": [str(python), "-m", "battery_detective", "collect", "--db", str(database)],
            "WorkingDirectory": str(project), "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 30,
            "ProcessType": "Background", "Nice": 10, "Umask": 0o077,
            "StandardOutPath": str(Path(logs) / "agent.stdout.log"),
            "StandardErrorPath": str(Path(logs) / "agent.stderr.log")}


def manage_agent(action, database, dry_run=False):
    if sys.platform != "darwin":
        raise ValueError("LaunchAgents require macOS.")
    plist_path = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    logs = Path.home() / "Library/Logs/Battery Detective"
    database = Path(database).expanduser().resolve()
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    definition = agent_definition(Path(sys.executable).absolute(), database,
                                  Path(__file__).resolve().parent.parent, logs)
    if dry_run:
        if action != "install":
            raise ValueError("--dry-run is available for agent install.")
        print(plistlib.dumps(definition).decode(), end="")
        return

    def launchctl(*args, check=True):
        result = subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True)
        if check and result.returncode:
            raise RuntimeError(result.stderr.strip() or f"launchctl {' '.join(args)} failed")
        return result

    loaded = launchctl("print", target, check=False).returncode == 0
    if action == "status":
        print(f"Installed: {'yes' if plist_path.exists() else 'no'}; loaded: {'yes' if loaded else 'no'}")
        if loaded:
            details = launchctl("print", target).stdout
            for line in details.splitlines():
                if any(key in line for key in ("state =", "pid =", "last exit code =")):
                    print(line.strip())
        return
    if action == "install":
        if plist_path.exists():
            raise ValueError("The agent is already installed. Use agent start, or uninstall before changing its configuration.")
        os.umask(0o077)
        logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        with plist_path.open("xb") as file:
            plistlib.dump(definition, file)
        print(f"Installed {plist_path}")
        print("Run battery-detective agent start to begin collecting now. It will also start at next login.")
    elif action == "start":
        if not plist_path.exists():
            raise ValueError("Install the agent first with: battery-detective agent install")
        if not loaded:
            launchctl("bootstrap", domain, str(plist_path))
        else:
            launchctl("kickstart", target)
        print("Collector agent started.")
    elif action in ("stop", "uninstall"):
        if loaded:
            launchctl("bootout", target)
        if action == "uninstall":
            plist_path.unlink(missing_ok=True)
            print("Agent uninstalled. Historical data and logs are preserved.")
        else:
            print("Collector agent stopped until the next start or login.")

