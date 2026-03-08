#!/usr/bin/env python3
"""
Productivity Dashboard — Flask web app
Serves analytics from the activity SQLite database.
Runs on http://localhost:5555
Background thread runs analysis every hour.
"""

import json
import sqlite3
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template

BASE_DIR  = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
import config_loader

_cfg      = config_loader.load()
DB_PATH   = Path(_cfg["data_dir"]) / "activity.db"
CATS_PATH = BASE_DIR / "categories.json"

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_categories() -> dict:
    with open(CATS_PATH) as f:
        return json.load(f)


def productivity_score(cat_secs: dict, total_active: float) -> int:
    """
    0-100 score.
    Productive categories (deep_work, terminal, docs, planning, ai_tools) add to score.
    Distraction subtracts.
    """
    if total_active <= 0:
        return 0
    productive  = sum(cat_secs.get(c, 0) for c in
                      ["deep_work", "terminal", "documentation", "planning", "ai_tools"])
    distraction = cat_secs.get("distraction", 0)
    score = (productive / total_active) * 100 - (distraction / total_active) * 35
    return max(0, min(100, int(score)))


def db_exists() -> bool:
    return DB_PATH.exists()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cats = load_categories()
    return render_template("index.html", categories=cats)


@app.route("/api/status")
def api_status():
    if not db_exists():
        return jsonify({"monitoring": False, "reason": "no database"})
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM activity ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return jsonify({
            "monitoring": True,
            "last_seen":  row["timestamp"],
            "app":        row["app"],
            "category":   row["category"],
        })
    return jsonify({"monitoring": False, "reason": "no data yet"})


@app.route("/api/today")
def api_today():
    today = date.today().isoformat()
    conn  = get_db()
    cats  = load_categories()

    rows = conn.execute("""
        SELECT category, SUM(duration_seconds) AS secs
        FROM activity
        WHERE timestamp >= ? AND category != 'idle'
        GROUP BY category
        ORDER BY secs DESC
    """, (today,)).fetchall()

    idle_row = conn.execute("""
        SELECT COALESCE(SUM(duration_seconds), 0) AS secs
        FROM activity
        WHERE timestamp >= ? AND category = 'idle'
    """, (today,)).fetchone()

    total_row = conn.execute("""
        SELECT COALESCE(SUM(duration_seconds), 0) AS secs,
               MIN(timestamp) AS first_seen
        FROM activity WHERE timestamp >= ?
    """, (today,)).fetchone()

    conn.close()

    cat_secs     = {r["category"]: r["secs"] for r in rows}
    total_active = sum(cat_secs.values())
    idle_secs    = idle_row["secs"]
    total_secs   = total_row["secs"]

    # Chart arrays sorted by time descending
    chart_labels, chart_values, chart_colors = [], [], []
    for cat, secs in sorted(cat_secs.items(), key=lambda x: x[1], reverse=True):
        if secs > 0:
            info = cats.get(cat, {})
            chart_labels.append(info.get("label", cat.replace("_", " ").title()))
            chart_values.append(round(secs / 60, 1))
            chart_colors.append(info.get("color", "#607D8B"))

    return jsonify({
        "score":                productivity_score(cat_secs, total_active),
        "total_active_minutes": round(total_active / 60, 1),
        "idle_minutes":         round(idle_secs    / 60, 1),
        "total_minutes":        round(total_secs   / 60, 1),
        "first_seen":           total_row["first_seen"] or today,
        "categories":           {cat: round(s / 60, 1) for cat, s in cat_secs.items()},
        "chart": {
            "labels": chart_labels,
            "values": chart_values,
            "colors": chart_colors,
        },
    })


@app.route("/api/weekly")
def api_weekly():
    conn = get_db()
    days = []
    for i in range(6, -1, -1):
        day_start = (date.today() - timedelta(days=i)).isoformat()
        day_end   = (date.today() - timedelta(days=i - 1)).isoformat()

        rows = conn.execute("""
            SELECT category, SUM(duration_seconds) AS secs
            FROM activity
            WHERE timestamp >= ? AND timestamp < ?
              AND category NOT IN ('idle', 'uncategorized')
            GROUP BY category
        """, (day_start, day_end)).fetchall()

        cat_secs = {r["category"]: r["secs"] for r in rows}
        total    = sum(cat_secs.values())

        productive  = sum(cat_secs.get(c, 0) for c in
                          ["deep_work", "terminal", "documentation", "planning", "ai_tools"])
        comm        = cat_secs.get("communication", 0) + cat_secs.get("meetings", 0)
        distraction = cat_secs.get("distraction", 0)
        other       = total - productive - comm - distraction

        day_dt = date.today() - timedelta(days=i)
        days.append({
            "date":                   day_start,
            "label":                  day_dt.strftime("%a"),
            "productive_minutes":     round(productive  / 60, 1),
            "communication_minutes":  round(comm        / 60, 1),
            "distraction_minutes":    round(distraction / 60, 1),
            "other_minutes":          round(max(other, 0) / 60, 1),
            "score":                  productivity_score(cat_secs, total) if total > 0 else 0,
        })

    conn.close()
    return jsonify(days)


@app.route("/api/timeline")
def api_timeline():
    """Hourly breakdown of today's activity."""
    today = date.today().isoformat()
    conn  = get_db()
    cats  = load_categories()

    rows = conn.execute("""
        SELECT strftime('%H', timestamp) AS hour,
               category,
               SUM(duration_seconds) AS secs
        FROM activity
        WHERE timestamp >= ?
        GROUP BY hour, category
        ORDER BY hour
    """, (today,)).fetchall()
    conn.close()

    hours: dict[int, dict] = {}
    for r in rows:
        h = int(r["hour"])
        hours.setdefault(h, {})[r["category"]] = round(r["secs"] / 60, 1)

    timeline = []
    for h in range(6, 24):
        hour_data = hours.get(h, {})
        total = sum(hour_data.values())
        if total < 0.5:
            continue
        dominant = max(hour_data, key=hour_data.get)
        info     = cats.get(dominant, {})
        timeline.append({
            "hour":            h,
            "label":           f"{h:02d}:00",
            "dominant":        dominant,
            "dominant_label":  info.get("label", dominant),
            "dominant_color":  info.get("color", "#607D8B"),
            "breakdown":       hour_data,
            "total_minutes":   round(total, 1),
        })

    return jsonify(timeline)


@app.route("/api/top-windows")
def api_top_windows():
    today = date.today().isoformat()
    conn  = get_db()

    rows = conn.execute("""
        SELECT app, window_title, category,
               COUNT(*) AS hits,
               SUM(duration_seconds) AS secs
        FROM activity
        WHERE timestamp >= ?
          AND window_title != ''
          AND window_title != 'unknown'
          AND length(window_title) > 3
        GROUP BY app, window_title
        ORDER BY secs DESC
        LIMIT 20
    """, (today,)).fetchall()
    conn.close()

    return jsonify([{
        "app":      r["app"],
        "window":   r["window_title"][:90],
        "minutes":  round(r["secs"] / 60, 1),
        "category": r["category"],
        "hits":     r["hits"],
    } for r in rows])


@app.route("/api/recommendations")
def api_recommendations():
    if not db_exists():
        return jsonify([])
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM recommendations
        WHERE dismissed = 0
        ORDER BY
            CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            created_at DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/dismiss/<int:rec_id>", methods=["POST"])
def api_dismiss(rec_id):
    conn = get_db()
    conn.execute("UPDATE recommendations SET dismissed = 1 WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/weekly-scores")
def api_weekly_scores():
    """Just the 7-day score history for the sparkline."""
    conn  = get_db()
    scores = []
    for i in range(6, -1, -1):
        day_start = (date.today() - timedelta(days=i)).isoformat()
        day_end   = (date.today() - timedelta(days=i - 1)).isoformat()
        rows = conn.execute("""
            SELECT category, SUM(duration_seconds) AS secs
            FROM activity WHERE timestamp >= ? AND timestamp < ?
              AND category NOT IN ('idle', 'uncategorized')
            GROUP BY category
        """, (day_start, day_end)).fetchall()
        cat_secs = {r["category"]: r["secs"] for r in rows}
        total    = sum(cat_secs.values())
        scores.append({
            "label": (date.today() - timedelta(days=i)).strftime("%a"),
            "score": productivity_score(cat_secs, total) if total > 0 else None,
        })
    conn.close()
    return jsonify(scores)


# ── Background analysis thread ────────────────────────────────────────────────

def analysis_loop():
    """Run analyze.py logic every hour in the background."""
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from analyze import analyze_patterns

    time.sleep(30)  # brief startup delay
    while True:
        try:
            analyze_patterns()
        except Exception as exc:
            print(f"[analyze] error: {exc}")
        time.sleep(3600)  # every hour


# ── Launch ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = threading.Thread(target=analysis_loop, daemon=True)
    t.start()
    app.run(host="127.0.0.1", port=_cfg["dashboard_port"], debug=False)
