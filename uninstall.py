#!/usr/bin/env python3
"""
Cross-platform uninstaller for Productivity Monitor.
Stops services and removes auto-start entries.
Data directory is preserved — delete manually if you want a clean slate.

Usage: python3 uninstall.py
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

OS       = platform.system()
BASE_DIR = Path(__file__).parent

_colour = OS != "Windows" or os.environ.get("WT_SESSION")
GRN = "\033[92m" if _colour else ""
YEL = "\033[93m" if _colour else ""
RED = "\033[91m" if _colour else ""
RST = "\033[0m"  if _colour else ""

def ok(msg):   print(f"{GRN}✓{RST} {msg}")
def warn(msg): print(f"{YEL}▲ {msg}{RST}")
def err(msg):  print(f"{RED}✗ {msg}{RST}")


def uninstall_macos():
    agents = Path.home() / "Library" / "LaunchAgents"
    labels = [
        "com.productivity-monitor.daemon",
        "com.productivity-monitor.dashboard",
    ]
    for label in labels:
        plist = agents / f"{label}.plist"
        if plist.exists():
            # Try both unload methods
            subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
            uid = os.getuid()
            subprocess.run(
                ["launchctl", "bootout", f"gui/{uid}", str(plist)],
                capture_output=True,
            )
            plist.unlink()
            ok(f"Removed {plist.name}")
        else:
            warn(f"Not found: {plist.name}")


def uninstall_linux():
    services = ["productivity-monitor", "productivity-dashboard"]
    for name in services:
        subprocess.run(["systemctl", "--user", "stop",    name], capture_output=True)
        subprocess.run(["systemctl", "--user", "disable", name], capture_output=True)

        svc = Path.home() / ".config" / "systemd" / "user" / f"{name}.service"
        if svc.exists():
            svc.unlink()
            ok(f"Removed {svc.name}")
        else:
            warn(f"Not found: {svc}")

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


def uninstall_windows():
    tasks = ["ProductivityMonitor", "ProductivityDashboard"]
    for name in tasks:
        r = subprocess.run(
            ["schtasks", "/delete", "/tn", f"ProductivityMonitor\\{name}", "/f"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            ok(f"Removed scheduled task: {name}")
        else:
            warn(f"Task not found or already removed: {name}")

    # Clean up wrapper .bat files
    for bat in BASE_DIR.glob("_productivity*.bat"):
        bat.unlink()
        ok(f"Removed {bat.name}")


def main():
    print("\n  Productivity Monitor — Uninstall\n")

    try:
        confirm = input("  Remove all services and auto-start entries? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if confirm != "y":
        print("  Aborted.")
        sys.exit(0)

    print()
    if OS == "Darwin":
        uninstall_macos()
    elif OS == "Linux":
        uninstall_linux()
    elif OS == "Windows":
        uninstall_windows()
    else:
        warn(f"Unknown OS '{OS}' — stop processes manually.")

    print()
    ok("Services removed.")
    print(f"  Your data is preserved. To delete it, remove the data directory")
    print(f"  shown in config.json → 'data_dir'.")
    print()


if __name__ == "__main__":
    main()
