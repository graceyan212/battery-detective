"""Optional native fields remain unknown when unavailable; no energy allocation."""

import plistlib
import subprocess
import sys
import psutil


def parse_power(properties):
    current = properties.get("Amperage")
    if isinstance(current, int) and current >= 2**63:
        current -= 2**64
    return {"charging": properties.get("IsCharging"), "voltage_mv": properties.get("Voltage"),
            "current_ma": current, "cycle_count": properties.get("CycleCount")}


def read_battery():
    errors = []
    try:
        battery = psutil.sensors_battery()
    except (OSError, NotImplementedError):
        battery = None
    result = {"battery_percent": battery.percent if battery else None,
              "plugged": battery.power_plugged if battery else None, **parse_power({})}
    if battery is None:
        errors.append("battery_unavailable")
    if sys.platform == "darwin":
        try:
            output = subprocess.run(["/usr/sbin/ioreg", "-r", "-c", "AppleSmartBattery", "-a"],
                                    capture_output=True, timeout=3, check=True)
            entries = plistlib.loads(output.stdout)
            if entries:
                result.update(parse_power(entries[0]))
            else:
                errors.append("native_battery_unavailable")
        except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
            errors.append("native_battery_unavailable")
    return result, errors
