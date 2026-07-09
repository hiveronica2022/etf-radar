#!/bin/bash
# 安装 ETF 份额雷达的 macOS 自动更新任务：
#   com.etf.radar.refresh  工作日 21:00 自动抓数并重建看板
#   com.etf.radar.serve    常驻本地 HTTP 服务 http://127.0.0.1:8765
# 重复运行本脚本会覆盖旧配置。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
AGENTS_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
# launchd 自身无法在 TCC 保护目录（如 ~/Desktop）打开 StandardOutPath，
# 否则按需 kickstart 会以 EX_CONFIG(78) 失败。日志改放 ~/Library/Logs。
LOG_DIR="$HOME/Library/Logs/etf-radar"

if [[ ! -x "$PYTHON" ]]; then
  echo "找不到 $PYTHON，请先创建虚拟环境并安装依赖：" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

REFRESH_PLIST="$AGENTS_DIR/com.etf.radar.refresh.plist"
SERVE_PLIST="$AGENTS_DIR/com.etf.radar.serve.plist"

cat > "$REFRESH_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.etf.radar.refresh</string>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/automation/refresh_and_publish.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>TQDM_DISABLE</key><string>1</string></dict>
  <key>StandardOutPath</key><string>$LOG_DIR/refresh.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/refresh.log</string>
</dict>
</plist>
PLIST

cat > "$SERVE_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.etf.radar.serve</string>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-m</string><string>http.server</string><string>8765</string>
    <string>--bind</string><string>127.0.0.1</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_DIR/serve.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/serve.log</string>
</dict>
</plist>
PLIST

# 让定时任务里的 git push 能用 gh 凭据非交互推送。
if command -v gh >/dev/null 2>&1; then
  gh auth setup-git 2>/dev/null && echo "configured git credential helper via gh"
fi

for label in com.etf.radar.refresh com.etf.radar.serve; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$AGENTS_DIR/$label.plist"
  echo "loaded $label"
done

echo
echo "安装完成："
echo "  本地看板   http://127.0.0.1:8765/dashboard/index.html"
echo "  数据刷新   工作日 21:00 自动抓取并推送到 GitHub Pages（日志 $LOG_DIR/refresh.log）"
echo "  手动触发   launchctl kickstart gui/$UID_NUM/com.etf.radar.refresh"
