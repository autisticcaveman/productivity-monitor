#!/usr/bin/env bash
# Uninstall — stops and removes the LaunchAgents
set -e
AGENTS="$HOME/Library/LaunchAgents"
for label in com.productivity-monitor.daemon com.productivity-monitor.dashboard; do
  plist="$AGENTS/$label.plist"
  if [ -f "$plist" ]; then
    launchctl unload "$plist" 2>/dev/null && echo "✓ Stopped $label" || true
    rm "$plist" && echo "✓ Removed $plist"
  else
    echo "  $label not found (already removed?)"
  fi
done
echo ""
echo "Done. Data is preserved in ./data/ — delete manually if you want a clean slate."
