#!/usr/bin/env python3
"""
Productivity Monitor Daemon
Polls active application every 30 seconds, logs to SQLite.
Cross-platform: macOS, Linux, Windows.
Configure paths and settings in config.json.
"""

import sqlite3
import json
import time
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

import config_loader
import platform_utils

_cfg           = config_loader.load()
BASE_DIR       = Path(__file__).parent
DATA_DIR       = Path(_cfg["data_dir"])
DB_PATH        = DATA_DIR / "activity.db"
CATS_PATH      = BASE_DIR / "categories.json"
POLL_INTERVAL  = _cfg["poll_interval_seconds"]
IDLE_THRESHOLD = _cfg["idle_threshold_seconds"]

logging.basicConfig(
    filename=str(DATA_DIR / "monitor.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_categories() -> dict:
    with open(CATS_PATH) as f:
        return json.load(f)


def get_active_app_and_window() -> tuple[str, str]:
    return platform_utils.get_active_app_and_window()


def get_idle_seconds() -> float:
    return platform_utils.get_idle_seconds()


def categorize(app: str, window: str, cats: dict) -> str:
    """Map app + window title to a productivity category."""
    a = app.lower()
    w = window.lower()
    for cat_name, cat_data in cats.items():
        if cat_name in ("idle", "uncategorized"):
            continue
        apps = [x.lower() for x in cat_data.get("apps", [])]
        if any(x in a for x in apps):
            for override in cat_data.get("window_overrides", []):
                keywords = [k.lower() for k in override.get("keywords", [])]
                if any(k in w for k in keywords):
                    return override["category"]
            return cat_name
    return "uncategorized"


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS activity (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        TEXT    NOT NULL,
            app              TEXT    NOT NULL,
            window_title     TEXT    DEFAULT "",
            category         TEXT    NOT NULL,
            idle_seconds     REAL    DEFAULT 0,
            duration_seconds REAL    DEFAULT 30
        );
        CREATE TABLE IF NOT EXISTS recommendations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT    NOT NULL,
            category   TEXT    DEFAULT "general",
            title      TEXT    NOT NULL,
            body       TEXT    NOT NULL,
            priority   TEXT    DEFAULT "medium",
            dismissed  INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ts  ON activity(timestamp);
        CREATE INDEX IF NOT EXISTS idx_cat ON activity(category);
    """)
    conn.commit()
    conn.close()
    logging.info(f"DB ready at {DB_PATH}")


def log_activity(app: str, window: str, category: str, idle: float):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO activity (timestamp, app, window_title, category, idle_seconds, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), app, window, category, idle, POLL_INTERVAL),
        )
        conn.commit()
    finally:
        conn.close()


# ── Seed initial recommendations ──────────────────────────────────────────────

INITIAL_RECS = [
    {
        "category": "automation",
        "title": "Build a ServiceNow MCP Server",
        "body": (
            "You manage 500+ labs tracked in ServiceNow/CMDB. An MCP server that exposes lab status, "
            "open tickets, and policy compliance state would let you query and act on this data directly "
            "from your AI assistant — no context switching to the web UI. Query: 'which labs have open "
            "policy violations' and get an answer in 2 seconds."
        ),
        "priority": "high",
    },
    {
        "category": "automation",
        "title": "Daily Lab Brief Agent (Morning Script)",
        "body": (
            "A login-triggered script that pulls overnight alerts, pending compliance violations, "
            "new devices detected on lab networks, and open ServiceNow tickets — formatted as a 2-minute "
            "daily brief and appended to your Obsidian vault. Know your day before you open Slack."
        ),
        "priority": "high",
    },
    {
        "category": "automation",
        "title": "Network Baseline + Drift Detection Agent",
        "body": (
            "Nmap-based agent that snapshots each lab's network on a schedule, diffs against the approved "
            "baseline, and alerts on unauthorized device additions or removals. Especially valuable for "
            "hardware labs where physical access is harder to audit. Output: daily drift report per lab."
        ),
        "priority": "high",
    },
    {
        "category": "automation",
        "title": "Policy Compliance Checker Agent",
        "body": (
            "An agent that runs your security policy checklist against the full lab inventory from CMDB. "
            "Outputs a prioritized list of violations with severity, lab owner, and suggested remediation. "
            "Pipe the output into a ServiceNow ticket batch-creator for zero-touch ticket generation."
        ),
        "priority": "high",
    },
    {
        "category": "tools",
        "title": "Script Template Library MCP",
        "body": (
            "A local MCP server that indexes your bash/python scripts for lab management tasks and makes "
            "them searchable by intent. 'Find me the script that does Nmap diff' returns the right file. "
            "Stops you rewriting the same tools and surfaces your past work when you need it."
        ),
        "priority": "medium",
    },
    {
        "category": "workflow",
        "title": "Batch Your Communication Windows",
        "body": (
            "Reactive Slack/email checking throughout the day is one of the biggest deep-work killers. "
            "Define 3 communication windows (e.g. 9am, 12pm, 4pm) and close messaging apps between them. "
            "For lab teams: set an async expectation — most things can wait 2 hours."
        ),
        "priority": "medium",
    },
    {
        "category": "workflow",
        "title": "End-of-Day Review + Tomorrow's 3 Priorities",
        "body": (
            "A 5-minute end-of-day ritual script: summarizes today's completed items from your session "
            "logs, prompts you to set 3 priorities for tomorrow, and appends everything to Obsidian. "
            "Provides closure (critical for ADHD) and eliminates the 'where was I' ramp-up each morning."
        ),
        "priority": "medium",
    },
    {
        "category": "tools",
        "title": "Goose Agent: Lab Onboarding Automation",
        "body": (
            "An AI agent (using Goose/Claude Agent SDK) that handles the lab onboarding workflow: "
            "create CMDB entry, configure initial network baseline, assign policy profile, generate "
            "ServiceNow ticket, and send confirmation to the lab owner. Currently likely all manual steps."
        ),
        "priority": "medium",
    },
    {
        "category": "automation",
        "title": "Build a Jira MCP Server",
        "body": (
            "If any of your labs or projects are tracked in Jira, an MCP server gives you direct "
            "query and write access from your AI assistant — search issues, update status, create "
            "tickets, and pull sprint summaries without touching the UI. Pairs well with the "
            "ServiceNow MCP: cross-reference CMDB lab entries against open Jira issues in one query."
        ),
        "priority": "medium",
    },
]


def seed_recommendations():
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
    if count == 0:
        now = datetime.now().isoformat()
        for r in INITIAL_RECS:
            conn.execute(
                "INSERT INTO recommendations (created_at, category, title, body, priority) VALUES (?,?,?,?,?)",
                (now, r["category"], r["title"], r["body"], r["priority"]),
            )
        conn.commit()
        logging.info(f"Seeded {len(INITIAL_RECS)} initial recommendations")
    conn.close()


# ── Main loop ─────────────────────────────────────────────────────────────────

def handle_signal(sig, frame):
    logging.info("Monitor shutting down.")
    sys.exit(0)


def run():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logging.info("=== Productivity monitor starting ===")
    init_db()
    seed_recommendations()

    cats = load_categories()

    while True:
        try:
            app, window = get_active_app_and_window()
            idle = get_idle_seconds()

            if idle > IDLE_THRESHOLD:
                category = "idle"
            else:
                category = categorize(app, window, cats)

            log_activity(app, window, category, idle)
            logging.debug(f"{app} | {window[:60]} | {category} | idle={idle:.0f}s")

        except Exception as exc:
            logging.error(f"Loop error: {exc}", exc_info=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
