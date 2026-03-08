#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Push productivity monitor to another Mac
#
# Usage:
#   bash deploy.sh              # uses REMOTE_HOST from .deployrc
#   bash deploy.sh user@newmac  # one-off override (also saves to .deployrc)
#
# What it does:
#   1. rsyncs all project code to the remote (excludes machine-specific data/)
#   2. SSHs in and runs install.sh on the remote
#   3. Exports your current recommendations to the Obsidian vault so the
#      remote can pick them up via vault-sync.sh
#
# Requirements:
#   - SSH key auth set up to the remote (ssh-copy-id user@host)
#   - Remote Mac has python3 available
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RC="$SCRIPT_DIR/.deployrc"

# ── Load config ───────────────────────────────────────────────────────────────
[ -f "$RC" ] && source "$RC"

# Override from arg
if [ -n "${1:-}" ]; then
  REMOTE_HOST="$1"
  sed -i '' "s|^REMOTE_HOST=.*|REMOTE_HOST=\"$1\"|" "$RC"
  echo "Saved $1 to .deployrc"
fi

# Prompt if still empty
if [ -z "${REMOTE_HOST:-}" ]; then
  read -rp "Remote Mac (user@hostname or user@ip): " REMOTE_HOST
  sed -i '' "s|^REMOTE_HOST=.*|REMOTE_HOST=\"$REMOTE_HOST\"|" "$RC"
  echo "Saved to .deployrc"
fi

REMOTE_PATH="${REMOTE_PATH:-$HOME/productivity-monitor}"
VAULT_PATH="${VAULT_PATH:-}"

echo ""
echo "══════════════════════════════════════════════"
echo "  Deploy → $REMOTE_HOST"
echo "  Remote path: $REMOTE_PATH"
echo "══════════════════════════════════════════════"

# ── 1. Verify SSH connectivity ────────────────────────────────────────────────
echo ""
echo "▸ Checking SSH connection..."
if ! ssh -o ConnectTimeout=8 -o BatchMode=yes "$REMOTE_HOST" "echo ok" &>/dev/null; then
  echo ""
  echo "  SSH failed. Set up key auth first:"
  echo "    ssh-keygen -t ed25519        # if you don't have a key yet"
  echo "    ssh-copy-id $REMOTE_HOST"
  echo ""
  exit 1
fi
echo "  ✓ Connected"

# ── 2. Ensure remote directory exists ────────────────────────────────────────
ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_PATH/data' '$REMOTE_PATH/dashboard/templates'"

# ── 3. rsync code (never touch data/) ────────────────────────────────────────
echo ""
echo "▸ Syncing files..."
rsync -az --progress \
  --exclude='data/' \
  --exclude='*.pid' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  "$SCRIPT_DIR/" \
  "$REMOTE_HOST:$REMOTE_PATH/"
echo "  ✓ Files synced"

# ── 4. Run install.py on remote ───────────────────────────────────────────────
echo ""
echo "▸ Running install.py on remote..."
ssh -t "$REMOTE_HOST" "cd '$REMOTE_PATH' && python3 install.py --defaults"

# ── 5. Export recommendations to vault so remote can import them ──────────────
echo ""
echo "▸ Exporting recommendations to sync folder..."
python3 "$SCRIPT_DIR/sync.py" export
echo "  ✓ Recommendations exported to vault"
echo ""
echo "  On the remote machine, run:"
echo "    python3 $REMOTE_PATH/sync.py import"
echo ""

echo "══════════════════════════════════════════════"
echo "  Deploy complete."
echo "  Dashboard will be at http://localhost:5555"
echo "  on the remote machine."
echo ""
echo "  Don't forget: grant Accessibility permission"
echo "  on the remote too (System Settings →"
echo "  Privacy & Security → Accessibility → Terminal)"
echo "══════════════════════════════════════════════"
echo ""
