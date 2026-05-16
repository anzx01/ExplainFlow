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

# 使用 Playwright 已下载的 Chrome，跳过 Remotion 重复下载
export REMOTION_CHROME_HEADLESS_SHELL="C:/Users/DELL/AppData/Local/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-win64/chrome-headless-shell.exe"

echo "[info] Starting Render Server on http://localhost:3001 ..."
node server.mjs 2>&1 | tee -a "$(dirname "$0")/../logs/render.log"
