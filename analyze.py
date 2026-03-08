#!/usr/bin/env python3
"""
Productivity Analyzer
Reads activity data from SQLite and generates pattern-based recommendations.
Called automatically by the dashboard (hourly background thread).
Can also be run standalone: python3 analyze.py
"""

import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "data" / "activity.db"

PRODUCTIVE_CATS  = {"deep_work", "terminal", "documentation", "planning", "ai_tools"}
DISTRACTION_CATS = {"distraction"}
COMM_CATS        = {"communication", "meetings"}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def upsert_recommendation(conn, category: str, title: str, body: str, priority: str):
    """Insert only if an undismissed rec with same title doesn't exist."""
    existing = conn.execute(
        "SELECT id FROM recommendations WHERE title = ? AND dismissed = 0", (title,)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO recommendations (created_at, category, title, body, priority) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), category, title, body, priority),
        )
        return True
    return False


def analyze_patterns():
    if not DB_PATH.exists():
        print("No database yet — monitor hasn't run.")
        return

    conn = get_db()
    recs_added = 0
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    # ── 1. Category totals (last 7 days) ─────────────────────────────────────
    rows = conn.execute("""
        SELECT category, SUM(duration_seconds) AS secs
        FROM activity
        WHERE timestamp >= ? AND category NOT IN ('idle', 'uncategorized')
        GROUP BY category
    """, (week_ago,)).fetchall()

    cat_secs = {r["category"]: r["secs"] for r in rows}
    total = sum(cat_secs.values())

    if total < 3600:  # need at least 1 hour of data
        print("Not enough data yet for pattern analysis.")
        conn.close()
        return

    productive  = sum(cat_secs.get(c, 0) for c in PRODUCTIVE_CATS)
    distraction = sum(cat_secs.get(c, 0) for c in DISTRACTION_CATS)
    comm        = sum(cat_secs.get(c, 0) for c in COMM_CATS)

    prod_pct  = (productive  / total) * 100
    dist_pct  = (distraction / total) * 100
    comm_pct  = (comm        / total) * 100
    browse_pct = (cat_secs.get("browsing", 0) / total) * 100

    # ── 2. Distraction alert ──────────────────────────────────────────────────
    if dist_pct > 12:
        priority = "high" if dist_pct > 25 else "medium"
        added = upsert_recommendation(conn,
            "focus",
            f"Distraction Alert: {dist_pct:.0f}% of active time (7-day avg)",
            (
                f"Over the past 7 days, {dist_pct:.0f}% of your active tracked time went to distracting "
                "content (YouTube, Reddit, social, etc.). For a knowledge worker, anything above ~10% "
                "starts fragmenting deep work sessions. Options: (1) block distraction sites during "
                "focus hours with Cold Turkey or Focus app, (2) use a scheduled 'distraction window' "
                "(e.g., 10 min/hour), (3) just knowing the number is often enough to change behavior."
            ),
            priority,
        )
        if added: recs_added += 1

    # ── 3. Low deep work ──────────────────────────────────────────────────────
    if prod_pct < 35:
        priority = "high" if prod_pct < 20 else "medium"
        added = upsert_recommendation(conn,
            "focus",
            f"Low Deep Work Time: {prod_pct:.0f}% of your week (target: 50%+)",
            (
                f"Only {prod_pct:.0f}% of your active time is in focused work modes (coding, terminal, "
                "docs, planning). Knowledge workers generally aim for 50-60%. Common causes: too much "
                "reactive Slack, frequent context switching, or unclear priorities. Fix: time-block "
                "90-minute deep work sessions in the morning before email/Slack. Protect them as meetings."
            ),
            priority,
        )
        if added: recs_added += 1

    # ── 4. Communication overload ─────────────────────────────────────────────
    if comm_pct > 35:
        added = upsert_recommendation(conn,
            "workflow",
            f"Communication is Consuming {comm_pct:.0f}% of Your Week",
            (
                f"Slack/email/meetings are eating {comm_pct:.0f}% of your tracked time. That's significant "
                "fragmentation. Tactics that work: (1) batch async comms to 3 windows/day, (2) move "
                "recurring sync meetings to async (Loom, written updates), (3) for lab teams: create "
                "a 'comms-by-priority' expectation so only fires need immediate response."
            ),
            "medium",
        )
        if added: recs_added += 1

    # ── 5. Heavy browser use ──────────────────────────────────────────────────
    if browse_pct > 25:
        added = upsert_recommendation(conn,
            "automation",
            f"Heavy Browser Use ({browse_pct:.0f}%) — Consider a Local Docs MCP",
            (
                f"You're spending {browse_pct:.0f}% of tracked time in a browser. If much of that is "
                "reading docs/references, a local documentation MCP server would let you query docs "
                "without leaving your AI assistant or editor. Tools like Zeal (offline docs) or a "
                "custom MCP over your bookmarked references can cut this significantly."
            ),
            "low",
        )
        if added: recs_added += 1

    # ── 6. Peak hour detection ────────────────────────────────────────────────
    hour_rows = conn.execute("""
        SELECT strftime('%H', timestamp) AS hour,
               SUM(duration_seconds) AS secs
        FROM activity
        WHERE timestamp >= ?
          AND category IN ('deep_work', 'terminal', 'documentation')
        GROUP BY hour
        ORDER BY secs DESC
        LIMIT 3
    """, (week_ago,)).fetchall()

    if hour_rows:
        peak = int(hour_rows[0]["hour"])
        label = f"{peak:02d}:00–{peak+1:02d}:00"
        added = upsert_recommendation(conn,
            "schedule",
            f"Peak Productivity Window: {label}",
            (
                f"Your data shows {label} is your highest-output hour for deep work. "
                "Protect it: no meetings, no Slack, notifications off. Schedule your hardest "
                "or most creative tasks here. If it's changing week to week, look at what "
                "you ate/slept beforehand — those are your real levers."
            ),
            "low",
        )
        if added: recs_added += 1

    # ── 7. Context switching ──────────────────────────────────────────────────
    all_rows = conn.execute("""
        SELECT timestamp, category FROM activity
        WHERE timestamp >= ?
        ORDER BY timestamp
    """, (week_ago,)).fetchall()

    if len(all_rows) > 20:
        switches = sum(
            1 for i in range(1, len(all_rows))
            if all_rows[i]["category"] != all_rows[i-1]["category"]
            and all_rows[i]["category"] not in ("idle", "uncategorized")
            and all_rows[i-1]["category"] not in ("idle", "uncategorized")
        )
        rate = switches / (total / 3600)  # per hour of active time
        if rate > 5:
            priority = "high" if rate > 10 else "medium"
            added = upsert_recommendation(conn,
                "focus",
                f"High Context Switching: ~{rate:.1f} mode changes/hour",
                (
                    f"You're switching between work modes (coding → browser → terminal → comms) "
                    f"about {rate:.1f} times per active hour. Each switch costs 15-25 min of cognitive "
                    "re-entry. Fix: task batching. Do all your email together, all your coding together. "
                    "Pomodoro (25 on / 5 off) naturally reduces this by creating commitment to one mode."
                ),
                priority,
            )
            if added: recs_added += 1

    conn.commit()
    conn.close()
    print(f"Analysis complete. Added {recs_added} new recommendations.")
    return recs_added


if __name__ == "__main__":
    analyze_patterns()
