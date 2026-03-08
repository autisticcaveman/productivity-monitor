#!/usr/bin/env python3
"""
Loads config.json and provides resolved settings to all other modules.
Falls back to sensible OS-appropriate defaults for any missing key.
"""

import json
import os
import platform
from pathlib import Path

BASE_DIR = Path(__file__).parent
_CONFIG_PATH = BASE_DIR / "config.json"

_OS = platform.system()  # 'Darwin' | 'Linux' | 'Windows'


def _default_data_dir() -> str:
    if _OS == "Darwin":
        return str(Path.home() / "Library" / "Application Support" / "productivity-monitor")
    elif _OS == "Linux":
        return str(Path.home() / ".local" / "share" / "productivity-monitor")
    elif _OS == "Windows":
        base = os.environ.get("APPDATA", str(Path.home()))
        return str(Path(base) / "productivity-monitor")
    return str(BASE_DIR / "data")


_DEFAULTS = {
    "data_dir":               "",
    "dashboard_port":         5555,
    "poll_interval_seconds":  30,
    "idle_threshold_seconds": 300,
    "sync_enabled":           False,
    "sync_path":              "",
    "auto_categorize":        True,
}


def load() -> dict:
    """Return fully resolved config dict. Always safe to call."""
    cfg = _DEFAULTS.copy()

    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH) as f:
                user = json.load(f)
            cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
        except Exception as e:
            print(f"[config] Warning: could not read config.json — {e}")

    # Resolve empty data_dir to OS default
    if not cfg.get("data_dir"):
        cfg["data_dir"] = _default_data_dir()

    # Ensure data dir exists
    Path(cfg["data_dir"]).mkdir(parents=True, exist_ok=True)

    return cfg


def db_path() -> Path:
    return Path(load()["data_dir"]) / "activity.db"


def sync_dir():
    cfg = load()
    if cfg.get("sync_enabled") and cfg.get("sync_path"):
        p = Path(cfg["sync_path"]) / "productivity-monitor"
        p.mkdir(parents=True, exist_ok=True)
        return p
    return None
