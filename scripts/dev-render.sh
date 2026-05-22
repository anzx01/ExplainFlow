#!/usr/bin/env bash
# 启动 Remotion Render Server（HTTP 渲染服务，端口 3001）
set -euo pipefail

cd "$(dirname "$0")/../apps/render"

if [ ! -d "node_modules" ]; then
  echo "[info] Installing Remotion dependencies..."
  npm install
fi

mkdir -p "$(dirname "$0")/../outputs"
mkdir -p "$(dirname "$0")/../logs"

# server.mjs 会自动扫描 %LOCALAPPDATA%/ms-playwright/ 下的 chrome-headless-shell。
# 如需手动指定，设置此环境变量（覆盖自动发现）：
# export REMOTION_CHROME_HEADLESS_SHELL="/path/to/chrome-headless-shell.exe"
# 首次使用前运行: cd apps/render && npx playwright install chromium

echo "[info] Starting Render Server on http://localhost:3001 ..."
node server.mjs 2>&1 | tee -a "$(dirname "$0")/../logs/render.log"
