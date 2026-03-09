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

from flask import Flask, jsonify, render_template, request, send_file

BASE_DIR  = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
import config_loader

_cfg        = config_loader.load()
DB_PATH     = Path(_cfg["data_dir"]) / "activity.db"
CATS_PATH   = BASE_DIR / "categories.json"
CONFIG_PATH = BASE_DIR / "config.json"

app = Flask(__name__)


@app.route("/favicon.ico")
def favicon():
    return "", 204


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


def categorize(app: str, window: str, cats: dict) -> str:
    """Map app + window title → category key. Mirror of monitor.py — keep in sync."""
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


def recategorize_recent(cats: dict, days: int = 7) -> int:
    """Retroactively update categories for recent non-idle records using new cats dict.
    Returns count of rows updated."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT id, app, window_title, category FROM activity "
        "WHERE timestamp >= ? AND category != 'idle'",
        (cutoff,),
    ).fetchall()
    updates = [
        (categorize(r["app"], r["window_title"] or "", cats), r["id"])
        for r in rows
        if categorize(r["app"], r["window_title"] or "", cats) != r["category"]
    ]
    if updates:
        conn.executemany("UPDATE activity SET category=? WHERE id=?", updates)
        conn.commit()
    conn.close()
    return len(updates)


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
            "keys":   [cat for cat, secs in sorted(cat_secs.items(), key=lambda x: x[1], reverse=True) if secs > 0],
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


# ── Settings / categories API ─────────────────────────────────────────────────

@app.route("/api/categories")
def api_get_categories():
    return jsonify(load_categories())


@app.route("/api/categories", methods=["POST"])
def api_save_categories():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400
    with open(CATS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    updated = recategorize_recent(data)
    return jsonify({"ok": True, "recategorized": updated})


@app.route("/api/config")
def api_get_config():
    cfg = config_loader.load()
    return jsonify({
        "auto_categorize":        cfg.get("auto_categorize", True),
        "poll_interval_seconds":  cfg["poll_interval_seconds"],
        "idle_threshold_seconds": cfg["idle_threshold_seconds"],
        "dashboard_port":         cfg["dashboard_port"],
    })


@app.route("/api/config", methods=["POST"])
def api_save_config():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400

    # Read current config file (preserve all keys we don't touch)
    current = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                current = json.load(f)
        except Exception:
            pass

    # Only allow safe dashboard-editable keys
    safe_keys = {"auto_categorize", "poll_interval_seconds", "idle_threshold_seconds", "dashboard_port"}
    for k, v in data.items():
        if k in safe_keys:
            current[k] = v

    with open(CONFIG_PATH, "w") as f:
        json.dump(current, f, indent=2)
    return jsonify({"ok": True})


# ── Logs API ─────────────────────────────────────────────────────────────────

@app.route("/api/logs")
def api_logs():
    log_name = request.args.get("log", "monitor")
    cfg      = config_loader.load()
    data_dir = Path(cfg["data_dir"])
    log_map  = {
        "monitor":       data_dir / "monitor.log",
        "monitor-out":   data_dir / "monitor-out.log",
        "monitor-err":   data_dir / "monitor-err.log",
        "dashboard":     data_dir / "dashboard-out.log",
        "dashboard-err": data_dir / "dashboard-err.log",
    }
    path = log_map.get(log_name)
    if not path:
        return jsonify({"error": "unknown log"}), 400
    if not path.exists():
        return jsonify({"lines": [], "exists": False, "path": str(path)})
    try:
        with open(path, errors="replace") as f:
            lines = f.readlines()
        return jsonify({
            "lines":  [l.rstrip() for l in lines[-200:]],
            "exists": True,
            "path":   str(path),
            "total":  len(lines),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Log download ─────────────────────────────────────────────────────────────

@app.route("/api/logs/download")
def api_logs_download():
    log_name = request.args.get("log", "monitor")
    cfg      = config_loader.load()
    data_dir = Path(cfg["data_dir"])
    log_map  = {
        "monitor":       data_dir / "monitor.log",
        "monitor-out":   data_dir / "monitor-out.log",
        "monitor-err":   data_dir / "monitor-err.log",
        "dashboard":     data_dir / "dashboard-out.log",
        "dashboard-err": data_dir / "dashboard-err.log",
    }
    path = log_map.get(log_name)
    if not path or not path.exists():
        return jsonify({"error": "log not found"}), 404
    return send_file(str(path), as_attachment=True, download_name=path.name)


# ── Score killers ─────────────────────────────────────────────────────────────

@app.route("/api/score-killers")
def api_score_killers():
    """Top 5 apps by time today in non-productive categories."""
    today = date.today().isoformat()
    conn  = get_db()
    rows  = conn.execute("""
        SELECT app, category, SUM(duration_seconds) AS secs
        FROM activity
        WHERE timestamp >= ?
          AND category NOT IN (
              'idle', 'deep_work', 'terminal', 'documentation', 'planning', 'ai_tools'
          )
        GROUP BY app
        ORDER BY secs DESC
        LIMIT 5
    """, (today,)).fetchall()
    conn.close()
    return jsonify([{
        "app":      r["app"],
        "category": r["category"],
        "minutes":  round(r["secs"] / 60, 1),
    } for r in rows])


# ── Browser breakdown ─────────────────────────────────────────────────────────

@app.route("/api/browser-breakdown")
def api_browser_breakdown():
    """Today's category breakdown filtered to browser apps only."""
    today = date.today().isoformat()
    cats  = load_categories()
    browser_apps = [a.lower() for a in cats.get("browsing", {}).get("apps", [])]

    empty = {"score": 0, "total_minutes": 0.0,
             "chart": {"labels": [], "values": [], "colors": [], "keys": []}}
    if not browser_apps:
        return jsonify(empty)

    placeholders = ",".join("?" * len(browser_apps))
    conn = get_db()
    rows = conn.execute(f"""
        SELECT category, SUM(duration_seconds) AS secs
        FROM activity
        WHERE timestamp >= ? AND category != 'idle'
          AND lower(app) IN ({placeholders})
        GROUP BY category
        ORDER BY secs DESC
    """, [today] + browser_apps).fetchall()
    conn.close()

    cat_secs     = {r["category"]: r["secs"] for r in rows}
    total_active = sum(cat_secs.values())

    chart_labels, chart_values, chart_colors, chart_keys = [], [], [], []
    for cat, secs in sorted(cat_secs.items(), key=lambda x: x[1], reverse=True):
        if secs > 0:
            info = cats.get(cat, {})
            chart_labels.append(info.get("label", cat.replace("_", " ").title()))
            chart_values.append(round(secs / 60, 1))
            chart_colors.append(info.get("color", "#607D8B"))
            chart_keys.append(cat)

    return jsonify({
        "score":         productivity_score(cat_secs, total_active),
        "total_minutes": round(total_active / 60, 1),
        "chart": {
            "labels": chart_labels,
            "values": chart_values,
            "colors": chart_colors,
            "keys":   chart_keys,
        },
    })


# ── Backup / Restore API ──────────────────────────────────────────────────────

@app.route("/api/backup")
def api_backup():
    cfg  = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    cats = json.loads(CATS_PATH.read_text())   if CATS_PATH.exists()   else {}
    return jsonify({
        "version":    "1.3.0",
        "created":    datetime.now().isoformat(timespec="seconds"),
        "config":     cfg,
        "categories": cats,
    })


@app.route("/api/restore", methods=["POST"])
def api_restore():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400
    errors = []
    if "config" in data:
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(data["config"], f, indent=2)
        except Exception as exc:
            errors.append(f"config: {exc}")
    if "categories" in data:
        try:
            with open(CATS_PATH, "w") as f:
                json.dump(data["categories"], f, indent=2)
        except Exception as exc:
            errors.append(f"categories: {exc}")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 500
    return jsonify({"ok": True})


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
