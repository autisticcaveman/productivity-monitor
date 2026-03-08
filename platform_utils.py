#!/usr/bin/env python3
"""
Platform abstraction layer.
Provides get_active_app_and_window() and get_idle_seconds() for:
  - macOS   (osascript + ioreg)
  - Linux   (xdotool + xprintidle)
  - Windows (pywin32 + ctypes)
"""

import logging
import platform
import re
import subprocess

OS = platform.system()


# ── macOS ─────────────────────────────────────────────────────────────────────

def _active_darwin() -> tuple[str, str]:
    script = """
    tell application "System Events"
        try
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            set windowTitle to ""
            try
                set windowTitle to name of first window of frontApp
            end try
            return appName & "|||" & windowTitle
        on error
            return "unknown|||"
        end try
    end tell
    """
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=5)
        out = r.stdout.strip()
        if "|||" in out:
            app, win = out.split("|||", 1)
            return app.strip(), win.strip()
        return out or "unknown", ""
    except Exception as exc:
        logging.warning(f"macOS window detect failed: {exc}")
        return "unknown", ""


def _idle_darwin() -> float:
    try:
        r = subprocess.run(["ioreg", "-c", "IOHIDSystem"],
                           capture_output=True, text=True, timeout=5)
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', r.stdout)
        if m:
            return int(m.group(1)) / 1_000_000_000
    except Exception as exc:
        logging.warning(f"macOS idle detect failed: {exc}")
    return 0.0


# ── Linux ─────────────────────────────────────────────────────────────────────

def _active_linux() -> tuple[str, str]:
    # Primary: xdotool
    try:
        win_id = subprocess.run(["xdotool", "getactivewindow"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
        if win_id:
            win_name = subprocess.run(["xdotool", "getwindowname", win_id],
                                      capture_output=True, text=True, timeout=5).stdout.strip()
            pid = subprocess.run(["xdotool", "getwindowpid", win_id],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            if pid:
                app = subprocess.run(["ps", "-p", pid, "-o", "comm="],
                                     capture_output=True, text=True, timeout=5).stdout.strip()
                return app or "unknown", win_name or ""
    except FileNotFoundError:
        logging.warning("xdotool not found. Install: sudo apt install xdotool")
    except Exception as exc:
        logging.warning(f"Linux xdotool failed: {exc}")

    # Fallback: wnck via python-wnck if available
    try:
        import gi
        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck
        screen = Wnck.Screen.get_default()
        screen.force_update()
        win = screen.get_active_window()
        if win:
            return win.get_class_instance_name() or "unknown", win.get_name() or ""
    except Exception:
        pass

    return "unknown", ""


def _idle_linux() -> float:
    # xprintidle (returns ms)
    try:
        r = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip()) / 1000.0
    except FileNotFoundError:
        pass
    except Exception as exc:
        logging.warning(f"xprintidle failed: {exc}")

    # xssstate fallback
    try:
        r = subprocess.run(["xssstate", "-i"], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip()) / 1000.0
    except Exception:
        pass

    return 0.0


# ── Windows ───────────────────────────────────────────────────────────────────

def _active_windows() -> tuple[str, str]:
    try:
        import win32gui
        import win32process
        import psutil

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            name = psutil.Process(pid).name().removesuffix(".exe")
        except Exception:
            name = "unknown"
        return name, title
    except ImportError:
        logging.warning("pywin32/psutil missing. Run: pip install pywin32 psutil")
        return "unknown", ""
    except Exception as exc:
        logging.warning(f"Windows window detect failed: {exc}")
        return "unknown", ""


def _idle_windows() -> float:
    try:
        import ctypes

        class _LASTINPUT(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        li = _LASTINPUT()
        li.cbSize = ctypes.sizeof(li)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
        elapsed_ms = ctypes.windll.kernel32.GetTickCount() - li.dwTime
        return elapsed_ms / 1000.0
    except Exception as exc:
        logging.warning(f"Windows idle detect failed: {exc}")
    return 0.0


# ── Public API ────────────────────────────────────────────────────────────────

def get_active_app_and_window() -> tuple[str, str]:
    """Return (app_name, window_title) for the focused window."""
    if OS == "Darwin":  return _active_darwin()
    if OS == "Linux":   return _active_linux()
    if OS == "Windows": return _active_windows()
    return "unknown", ""


def get_idle_seconds() -> float:
    """Return seconds since last keyboard/mouse input."""
    if OS == "Darwin":  return _idle_darwin()
    if OS == "Linux":   return _idle_linux()
    if OS == "Windows": return _idle_windows()
    return 0.0


def platform_notes() -> list[str]:
    """Return post-install notes relevant to this OS."""
    if OS == "Darwin":
        return [
            "Grant Accessibility permission so the monitor can read app names:",
            "  System Settings → Privacy & Security → Accessibility → add Terminal",
        ]
    if OS == "Linux":
        return [
            "Install xdotool for app/window tracking:",
            "  Ubuntu/Debian:  sudo apt install xdotool",
            "  Fedora:         sudo dnf install xdotool",
            "  Arch:           sudo pacman -S xdotool",
            "Optional — idle detection:",
            "  sudo apt install xprintidle",
        ]
    if OS == "Windows":
        return [
            "Allow Python through Windows Firewall when prompted (for localhost:5555)",
            "If the dashboard doesn't start, run manually:",
            "  python dashboard\\app.py",
        ]
    return []
