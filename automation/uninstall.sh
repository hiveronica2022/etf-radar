#!/bin/bash
# 卸载 ETF 份额雷达的自动更新任务。
set -euo pipefail

AGENTS_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

for label in com.etf.radar.refresh com.etf.radar.serve; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$AGENTS_DIR/$label.plist"
  echo "removed $label"
done
