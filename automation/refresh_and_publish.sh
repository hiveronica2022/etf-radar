#!/bin/bash
# launchd 定时任务入口：抓取最新数据 → 重建单文件和 Pages 站点 → 推送到 GitHub。
# 数据抓取成功后即落盘；git 步骤失败只记录日志，不影响本地数据。
set -uo pipefail

# launchd 环境 PATH 很精简，显式补上 git / gh。
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python"

echo "=== refresh_and_publish $(date '+%Y-%m-%d %H:%M:%S') ==="

"$PYTHON" -m etf_radar.cli refresh \
  --preset core --preset bond --preset dividend \
  --window-set full --no-proxy \
  --retries 4 --retry-sleep 1.5 --price-pause 0.6 --max-passes 3 \
  --pages-out docs
refresh_status=$?
if [[ $refresh_status -ne 0 ]]; then
  echo "refresh failed (exit $refresh_status), skip publish"
  exit $refresh_status
fi

if [[ ! -d "$ROOT/.git" ]]; then
  echo "not a git repo, skip publish"
  exit 0
fi

# 只有 docs/ 或快照有变化时才提交推送。
git add docs data/dashboard_snapshot.json
if git diff --cached --quiet; then
  echo "no changes to publish"
  exit 0
fi

as_of="$("$PYTHON" -c "import json;print(json.load(open('data/dashboard_snapshot.json'))['meta']['as_of'])" 2>/dev/null || echo unknown)"
git commit -m "data: refresh as_of ${as_of}" >/dev/null
# 先 rebase 拉取远端（可能有 Actions 云端推送），避免非快进冲突。
git pull --rebase --autostash origin main >/dev/null 2>&1 || true
if git push 2>&1; then
  echo "published as_of ${as_of}"
else
  echo "git push failed — 检查 gh 登录 / 网络；本地数据已更新"
  exit 1
fi
