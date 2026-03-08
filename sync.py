#!/usr/bin/env python3
"""
Cross-platform recommendation sync.
Replaces vault-sync.sh — works on macOS, Linux, and Windows.

Syncs via any shared folder configured in config.json → sync_path.
This can be an Obsidian vault, Dropbox, OneDrive, a network share,
or any directory both machines can read/write.

Usage:
  python3 sync.py export   — write local recommendations → sync folder
  python3 sync.py import   — read sync folder → local DB (skips duplicates)
  python3 sync.py status   — show what's currently in the sync folder
  python3 sync.py path     — print the resolved sync folder path
"""

import json
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
import config_loader

_cfg     = config_loader.load()
DB_PATH  = Path(_cfg["data_dir"]) / "activity.db"
SYNC_DIR = config_loader.sync_dir()
SYNC_FILE = (SYNC_DIR / "recommendations.json") if SYNC_DIR else None


# ── Guards ────────────────────────────────────────────────────────────────────

def _check_sync_configured():
    if not SYNC_FILE:
        print(
            "Sync is not configured.\n"
            "Edit config.json and set:\n"
            '  "sync_enabled": true,\n'
            '  "sync_path": "/path/to/shared/folder"\n'
            "Then re-run."
        )
        sys.exit(1)


def _check_db():
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH} — run the monitor first.")
        sys.exit(1)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_export():
    _check_sync_configured()
    _check_db()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT category, title, body, priority
        FROM recommendations
        WHERE dismissed = 0
        ORDER BY
            CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            created_at
    """).fetchall()
    conn.close()

    payload = {
        "exported_at":   datetime.now().isoformat(),
        "source_host":   socket.gethostname(),
        "recommendations": [dict(r) for r in rows],
    }
    SYNC_FILE.write_text(json.dumps(payload, indent=2))
    print(f"Exported {len(rows)} recommendations → {SYNC_FILE}")


def cmd_import():
    _check_sync_configured()
    _check_db()

    if not SYNC_FILE.exists():
        print(
            f"No sync file found at {SYNC_FILE}\n"
            "Run 'python3 sync.py export' on the source machine first."
        )
        sys.exit(1)

    payload = json.loads(SYNC_FILE.read_text())
    recs    = payload.get("recommendations", [])
    source  = payload.get("source_host", "unknown")
    ts      = payload.get("exported_at", "")

    conn    = sqlite3.connect(DB_PATH)
    added   = 0
    skipped = 0

    for r in recs:
        exists = conn.execute(
            "SELECT id FROM recommendations WHERE title = ? AND dismissed = 0",
            (r["title"],),
        ).fetchone()
        if exists:
            skipped += 1
        else:
            conn.execute(
                "INSERT INTO recommendations (created_at, category, title, body, priority) "
                "VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(), r["category"], r["title"], r["body"], r["priority"]),
            )
            added += 1

    conn.commit()
    conn.close()
    print(f"Imported from {source} (exported {ts})")
    print(f"Added: {added}  |  Already present: {skipped}")


def cmd_status():
    _check_sync_configured()

    if not SYNC_FILE.exists():
        print(f"No sync file at {SYNC_FILE}")
        return

    p    = json.loads(SYNC_FILE.read_text())
    recs = p.get("recommendations", [])
    print(f"Source:    {p.get('source_host', '?')}")
    print(f"Exported:  {p.get('exported_at', '?')}")
    print(f"Count:     {len(recs)}")
    print()
    for r in recs:
        print(f"  [{r['priority']:6}]  {r['title']}")


def cmd_path():
    if SYNC_FILE:
        print(str(SYNC_FILE))
    else:
        print("(sync not configured)")


# ── Entry point ───────────────────────────────────────────────────────────────

COMMANDS = {
    "export": cmd_export,
    "import": cmd_import,
    "status": cmd_status,
    "path":   cmd_path,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(0 if cmd in ("", "-h", "--help") else 1)
    COMMANDS[cmd]()
