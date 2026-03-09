#!/usr/bin/env python3
"""
Cross-platform installer for Productivity Monitor.
Works on macOS, Linux, and Windows.

Usage:
  python3 install.py              # interactive
  python3 install.py --defaults   # accept all defaults (non-interactive)
  python3 install.py --uninstall  # remove services (same as uninstall.py)
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

OS       = platform.system()
PY       = sys.executable
BASE_DIR = Path(__file__).parent

# ── Terminal colours (disabled on Windows unless Windows Terminal) ─────────────
_colour  = OS != "Windows" or os.environ.get("WT_SESSION")
GRN = "\033[92m" if _colour else ""
YEL = "\033[93m" if _colour else ""
RED = "\033[91m" if _colour else ""
DIM = "\033[2m"  if _colour else ""
RST = "\033[0m"  if _colour else ""

def ok(msg):   print(f"{GRN}✓{RST} {msg}")
def info(msg): print(f"  {msg}")
def warn(msg): print(f"{YEL}▲ {msg}{RST}")
def err(msg):  print(f"{RED}✗ {msg}{RST}")
def hr():      print(f"{DIM}{'─'*52}{RST}")
def banner(t): print(f"\n{'═'*52}\n  {t}\n{'═'*52}")


def ask(prompt: str, default: str = "") -> str:
    if "--defaults" in sys.argv:
        return default
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        return default


def ask_port(default: int = 5555) -> int:
    """Ask for a port number, validate range, re-prompt on bad input."""
    while True:
        raw = ask(f"Dashboard port  (access via http://localhost:PORT)", str(default))
        try:
            p = int(raw)
            if 1024 <= p <= 65535:
                return p
            warn(f"Port must be between 1024 and 65535 (got {p})")
        except ValueError:
            warn(f"'{raw}' is not a valid port number — enter an integer")
        # In --defaults mode ask() returns the default string immediately;
        # if it somehow fails validation just fall back silently.
        if "--defaults" in sys.argv:
            return default


# ── Defaults per OS ───────────────────────────────────────────────────────────

def default_data_dir() -> str:
    if OS == "Darwin":
        return str(Path.home() / "Library" / "Application Support" / "productivity-monitor")
    if OS == "Linux":
        return str(Path.home() / ".local" / "share" / "productivity-monitor")
    if OS == "Windows":
        base = os.environ.get("APPDATA", str(Path.home()))
        return str(Path(base) / "productivity-monitor")
    return str(BASE_DIR / "data")


# ── Dependency installation ───────────────────────────────────────────────────

def install_deps():
    info("Installing Python dependencies…")
    pkgs = ["flask"]
    if OS == "Windows":
        pkgs += ["pywin32", "psutil"]

    for pkg in pkgs:
        r = subprocess.run(
            [PY, "-m", "pip", "install", pkg, "--quiet"],
            capture_output=True,
        )
        if r.returncode != 0:
            subprocess.run(
                [PY, "-m", "pip", "install", pkg, "--quiet", "--break-system-packages"],
                capture_output=True,
            )
    ok(f"Dependencies ready: {', '.join(pkgs)}")


# ── macOS LaunchAgents ────────────────────────────────────────────────────────

def _macos_plist(label: str, script: str, data_dir: str) -> str:
    log_stem = label.split(".")[-1]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{PY}</string>
        <string>{BASE_DIR / script}</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key>
    <string>{data_dir}/{log_stem}-out.log</string>
    <key>StandardErrorPath</key>
    <string>{data_dir}/{log_stem}-err.log</string>
</dict>
</plist>"""


def setup_macos(data_dir: str):
    agents = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)

    services = [
        ("com.productivity-monitor.daemon",   "monitor.py"),
        ("com.productivity-monitor.dashboard", "dashboard/app.py"),
    ]
    for label, script in services:
        plist = agents / f"{label}.plist"
        plist.write_text(_macos_plist(label, script, data_dir))

        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        r = subprocess.run(["launchctl", "load", str(plist)], capture_output=True)
        if r.returncode != 0:
            uid = os.getuid()
            subprocess.run(
                ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
                capture_output=True,
            )
        ok(f"LaunchAgent: {label}")


# ── Linux systemd user services ───────────────────────────────────────────────

def _linux_unit(script: str, data_dir: str) -> str:
    name = Path(script).stem
    return f"""[Unit]
Description=Productivity Monitor — {name}
After=graphical-session.target

[Service]
Type=simple
ExecStart={PY} {BASE_DIR / script}
Restart=always
RestartSec=10
StandardOutput=append:{data_dir}/{name}-out.log
StandardError=append:{data_dir}/{name}-err.log

[Install]
WantedBy=default.target
"""


def setup_linux(data_dir: str):
    svc_dir = Path.home() / ".config" / "systemd" / "user"
    svc_dir.mkdir(parents=True, exist_ok=True)

    services = [
        ("productivity-monitor",   "monitor.py"),
        ("productivity-dashboard", "dashboard/app.py"),
    ]
    for name, script in services:
        (svc_dir / f"{name}.service").write_text(_linux_unit(script, data_dir))

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)

    for name, _ in services:
        subprocess.run(["systemctl", "--user", "enable", name], capture_output=True)
        r = subprocess.run(["systemctl", "--user", "start",  name], capture_output=True)
        if r.returncode == 0:
            ok(f"systemd service: {name}")
        else:
            warn(f"Could not start {name} — try: systemctl --user start {name}")


# ── Windows Task Scheduler ────────────────────────────────────────────────────

def setup_windows(data_dir: str):
    services = [
        ("ProductivityMonitor",   "monitor.py"),
        ("ProductivityDashboard", str(Path("dashboard") / "app.py")),
    ]
    for name, script in services:
        script_path = BASE_DIR / script
        log_path    = Path(data_dir) / f"{name.lower()}-out.log"

        # Wrapper .bat so Task Scheduler can redirect output
        bat = BASE_DIR / f"_{name.lower()}.bat"
        bat.write_text(f'@echo off\n"{PY}" "{script_path}" >> "{log_path}" 2>&1\n')

        cmd = [
            "schtasks", "/create",
            "/tn", f"ProductivityMonitor\\{name}",
            "/tr", f'"{bat}"',
            "/sc", "ONLOGON",
            "/ru", os.environ.get("USERNAME", "CURRENTUSER"),
            "/f",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            subprocess.run(
                ["schtasks", "/run", "/tn", f"ProductivityMonitor\\{name}"],
                capture_output=True,
            )
            ok(f"Scheduled task: {name}")
        else:
            err(f"Could not create task {name}: {r.stderr.strip()}")
            info(f"  Start manually: {PY} {script_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    banner(f"Productivity Monitor v1.3.0 — Installer  [{OS}]")

    print(f"\n  Python:   {PY}")
    print(f"  Platform: {platform.version()[:60]}")
    hr()
    print("\n  Configure your installation.")
    print(f"  {DIM}Press Enter to accept defaults.{RST}\n")

    data_dir    = ask("Data directory (SQLite DB + logs)", default_data_dir())
    port        = ask_port(5555)
    poll        = ask("Poll interval seconds", "30")
    idle        = ask("Idle threshold seconds", "300")

    print()
    hr()
    print("\n  Recommendation sync lets both machines share the same")
    print("  list of tool/workflow suggestions via any shared folder.")
    print(f"  {DIM}(Obsidian vault, Dropbox, OneDrive, network share, etc.){RST}\n")
    want_sync = ask("Enable recommendation sync? (y/n)", "n").lower() == "y"
    sync_path = ""
    if want_sync:
        sync_path = ask("Path to shared sync folder")

    # ── Write config.json ─────────────────────────────────────────────────────
    cfg = {
        "_readme":               "Edit these values and re-run install.py to reconfigure — or use the dashboard Settings panel (⚙ top-right)",
        "_sync_note":            "sync_path can be any folder both machines can read/write",
        "_auto_cat_note":        "auto_categorize: false stops all name-matching — everything logs as uncategorized until re-enabled",
        "data_dir":              data_dir,
        "dashboard_port":        port,
        "poll_interval_seconds": int(poll),
        "idle_threshold_seconds": int(idle),
        "sync_enabled":          want_sync,
        "sync_path":             sync_path,
        "auto_categorize":       True,
    }
    cfg_path = BASE_DIR / "config.json"
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    ok(f"Config written → {cfg_path}")

    # ── Create data dir ───────────────────────────────────────────────────────
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    ok(f"Data directory  → {data_dir}")

    # ── Dependencies ──────────────────────────────────────────────────────────
    print()
    install_deps()

    # ── Services ──────────────────────────────────────────────────────────────
    print()
    if OS == "Darwin":
        setup_macos(data_dir)
    elif OS == "Linux":
        setup_linux(data_dir)
    elif OS == "Windows":
        setup_windows(data_dir)
    else:
        warn(f"Unrecognised OS '{OS}'. Start services manually:")
        info(f"  {PY} {BASE_DIR / 'monitor.py'}")
        info(f"  {PY} {BASE_DIR / 'dashboard' / 'app.py'}")

    # ── Post-install notes ────────────────────────────────────────────────────
    print()
    banner("Installation Complete")
    info(f"Dashboard  →  http://localhost:{port}")
    info(f"Data dir   →  {data_dir}")
    info(f"Config     →  {cfg_path}")
    print()

    # Platform-specific reminders
    import platform_utils
    notes = platform_utils.platform_notes()
    if notes:
        hr()
        warn("IMPORTANT — additional steps required:")
        for n in notes:
            info(f"  {n}")
        print()

    if want_sync:
        hr()
        info("Sync is enabled. On the other machine after installing:")
        info(f"  python3 sync.py import")
        print()


if __name__ == "__main__":
    main()
