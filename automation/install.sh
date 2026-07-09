#!/bin/bash
# 安装 ETF 份额雷达的 macOS 后台任务：
#   com.etf.radar.serve    常驻本地 HTTP 服务 http://127.0.0.1:8765（本地查看）
#   com.etf.radar.refresh  可选：工作日 21:00 本机抓数并推送到 GitHub（默认关闭）
#
# 数据更新默认由 GitHub Actions 在云端完成（不用开机）。若还想在本机也跑一份
# 备份更新，用 ETF_LOCAL_REFRESH=1 bash automation/install.sh 开启。
# 重复运行本脚本会覆盖旧配置。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
AGENTS_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LOCAL_REFRESH="${ETF_LOCAL_REFRESH:-0}"
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

# 先卸载再加载；launchctl 卸载后需要短暂等待释放，否则 bootstrap 会报 I/O error。
reload_agent() {
  local label="$1" plist="$2"
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  sleep 2
  launchctl bootstrap "gui/$UID_NUM" "$plist" 2>/dev/null \
    || { sleep 2; launchctl bootstrap "gui/$UID_NUM" "$plist"; }
}

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

# serve agent 始终安装。
reload_agent com.etf.radar.serve "$SERVE_PLIST"
echo "loaded com.etf.radar.serve"

if [[ "$LOCAL_REFRESH" == "1" ]]; then
  # 让本机 cron 里的 git push 能用 gh 凭据非交互推送。
  if command -v gh >/dev/null 2>&1; then
    gh auth setup-git 2>/dev/null && echo "configured git credential helper via gh"
  fi
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
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>30</integer></dict>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>TQDM_DISABLE</key><string>1</string></dict>
  <key>StandardOutPath</key><string>$LOG_DIR/refresh.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/refresh.log</string>
</dict>
</plist>
PLIST
  reload_agent com.etf.radar.refresh "$REFRESH_PLIST"
  echo "loaded com.etf.radar.refresh（本机备份更新，工作日 21:30，晚于云端以免撞车）"
else
  # 默认不装本机刷新 cron：云端 GitHub Actions 负责更新。移除历史遗留的。
  launchctl bootout "gui/$UID_NUM/com.etf.radar.refresh" 2>/dev/null || true
  rm -f "$REFRESH_PLIST"
fi

echo
echo "安装完成："
echo "  本地看板   http://127.0.0.1:8765/dashboard/index.html"
echo "  公开网址   由 GitHub Pages 托管，GitHub Actions 工作日 21:00（北京）云端自动更新"
if [[ "$LOCAL_REFRESH" == "1" ]]; then
  echo "  本机备份   工作日 21:30 也在本机抓一份并推送（日志 $LOG_DIR/refresh.log）"
  echo "  手动触发   launchctl kickstart gui/$UID_NUM/com.etf.radar.refresh"
else
  echo "  本机刷新   默认关闭（ETF_LOCAL_REFRESH=1 bash automation/install.sh 可开启备份更新）"
fi
