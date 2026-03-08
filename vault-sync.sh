#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# vault-sync.sh — Share recommendations between machines via Obsidian vault
#
# Both Macs mount the same Obsidian vault, so this file acts as the sync bus.
# Recommendations are machine-agnostic (tool suggestions, workflow tips) —
# activity data is NOT synced (it's machine-specific).
#
# Usage:
#   bash vault-sync.sh export   # write local recs → vault JSON
#   bash vault-sync.sh import   # read vault JSON → local DB (skips dupes)
#   bash vault-sync.sh status   # show what's in the vault file
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RC="$SCRIPT_DIR/.deployrc"
[ -f "$RC" ] && source "$RC"

DB_PATH="$SCRIPT_DIR/data/activity.db"
VAULT_PATH="${VAULT_PATH:-~/your-sync-folder}"
SYNC_DIR="$VAULT_PATH/productivity-monitor"
SYNC_FILE="$SYNC_DIR/recommendations.json"

CMD="${1:-}"

if [ -z "$CMD" ]; then
  echo "Usage: bash vault-sync.sh [export|import|status]"
  exit 1
fi

case "$CMD" in

  # ── Export: local DB → vault JSON ─────────────────────────────────────────
  export)
    if [ ! -f "$DB_PATH" ]; then
      echo "No database at $DB_PATH — monitor hasn't run yet."
      exit 1
    fi
    mkdir -p "$SYNC_DIR"

    python3 - "$DB_PATH" "$SYNC_FILE" << 'PYEOF'
import sqlite3, json, sys
from datetime import datetime

db_path   = sys.argv[1]
out_path  = sys.argv[2]

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT category, title, body, priority
    FROM recommendations
    WHERE dismissed = 0
    ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at
""").fetchall()
conn.close()

payload = {
    "exported_at": datetime.now().isoformat(),
    "source_host": __import__('socket').gethostname(),
    "recommendations": [dict(r) for r in rows],
}

with open(out_path, "w") as f:
    json.dump(payload, f, indent=2)

print(f"  Exported {len(rows)} recommendations → {out_path}")
PYEOF
    ;;

  # ── Import: vault JSON → local DB (no duplicates) ─────────────────────────
  import)
    if [ ! -f "$SYNC_FILE" ]; then
      echo "No vault sync file found at $SYNC_FILE"
      echo "Run 'bash vault-sync.sh export' on the source machine first."
      exit 1
    fi
    if [ ! -f "$DB_PATH" ]; then
      echo "No local database yet — run the monitor first, then import."
      exit 1
    fi

    python3 - "$DB_PATH" "$SYNC_FILE" << 'PYEOF'
import sqlite3, json, sys
from datetime import datetime

db_path  = sys.argv[1]
in_path  = sys.argv[2]

with open(in_path) as f:
    payload = json.load(f)

recs   = payload.get("recommendations", [])
source = payload.get("source_host", "unknown")
ts     = payload.get("exported_at", "")

conn = sqlite3.connect(db_path)
added = 0
skipped = 0

for r in recs:
    existing = conn.execute(
        "SELECT id FROM recommendations WHERE title = ? AND dismissed = 0",
        (r["title"],)
    ).fetchone()
    if existing:
        skipped += 1
    else:
        conn.execute(
            "INSERT INTO recommendations (created_at, category, title, body, priority) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), r["category"], r["title"], r["body"], r["priority"])
        )
        added += 1

conn.commit()
conn.close()
print(f"  Imported from {source} (exported {ts})")
print(f"  Added: {added}  |  Already present: {skipped}")
PYEOF
    ;;

  # ── Status: show what's in the vault file ─────────────────────────────────
  status)
    if [ ! -f "$SYNC_FILE" ]; then
      echo "No vault sync file at $SYNC_FILE"
      exit 0
    fi
    python3 - "$SYNC_FILE" << 'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    p = json.load(f)
print(f"Source:    {p.get('source_host','?')}")
print(f"Exported:  {p.get('exported_at','?')}")
print(f"Count:     {len(p.get('recommendations',[]))}")
print()
for r in p.get("recommendations", []):
    print(f"  [{r['priority']:6}] {r['title']}")
PYEOF
    ;;

  *)
    echo "Unknown command: $CMD"
    echo "Usage: bash vault-sync.sh [export|import|status]"
    exit 1
    ;;
esac
