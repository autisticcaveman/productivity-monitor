#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Productivity Monitor — Install Script
# Sets up the activity monitor and dashboard as macOS LaunchAgents
# Run once: bash install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
MON_LABEL="com.productivity-monitor.daemon"
DASH_LABEL="com.productivity-monitor.dashboard"

echo ""
echo "══════════════════════════════════════════════"
echo "  Productivity Monitor Setup"
echo "  Project: $SCRIPT_DIR"
echo "══════════════════════════════════════════════"
echo ""

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install via: brew install python"
  exit 1
fi
PYTHON="$(which python3)"
echo "✓ Python: $PYTHON"

# ── Install Flask ─────────────────────────────────────────────────────────────
echo "  Installing Python dependencies..."
pip3 install flask --quiet --break-system-packages 2>/dev/null || pip3 install flask --quiet
echo "✓ Flask installed"

# ── Data dir ─────────────────────────────────────────────────────────────────
mkdir -p "$SCRIPT_DIR/data"
echo "✓ Data directory ready"

# ── Monitor LaunchAgent ───────────────────────────────────────────────────────
cat > "$AGENTS_DIR/$MON_LABEL.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${MON_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${SCRIPT_DIR}/monitor.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/data/monitor-out.log</string>
    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/data/monitor-err.log</string>
</dict>
</plist>
EOF

# ── Dashboard LaunchAgent ─────────────────────────────────────────────────────
cat > "$AGENTS_DIR/$DASH_LABEL.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${DASH_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${SCRIPT_DIR}/dashboard/app.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/data/dashboard-out.log</string>
    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/data/dashboard-err.log</string>
</dict>
</plist>
EOF

echo "✓ LaunchAgent plists written"

# ── Load agents ───────────────────────────────────────────────────────────────
echo "  Loading LaunchAgents..."
launchctl unload "$AGENTS_DIR/$MON_LABEL.plist"  2>/dev/null || true
launchctl unload "$AGENTS_DIR/$DASH_LABEL.plist" 2>/dev/null || true
launchctl load   "$AGENTS_DIR/$MON_LABEL.plist"
launchctl load   "$AGENTS_DIR/$DASH_LABEL.plist"

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Monitor:    running (polls every 30s)"
echo "  Dashboard:  http://localhost:5555"
echo ""
echo "  IMPORTANT — Accessibility Permission:"
echo "  System Settings → Privacy & Security → Accessibility"
echo "  Add: Terminal (or iTerm2) to allow window tracking"
echo ""
echo "  Logs:"
echo "    Monitor:   $SCRIPT_DIR/data/monitor.log"
echo "    Dashboard: $SCRIPT_DIR/data/dashboard-out.log"
echo ""
echo "  To open dashboard now:"
echo "    open http://localhost:5555"
echo "══════════════════════════════════════════════"
echo ""

# Give the dashboard a moment to start, then open it
sleep 3
open http://localhost:5555 2>/dev/null || true
