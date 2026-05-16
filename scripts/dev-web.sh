#!/usr/bin/env bash
# 启动 Next.js 前端开发服务器
set -euo pipefail

cd "$(dirname "$0")/../apps/web"

if [ ! -f ".env.local" ]; then
  echo "[warn] .env.local not found, copying from .env.local.example"
  cp .env.local.example .env.local
fi

echo "[info] Starting Next.js dev server on http://localhost:3000 ..."
node_modules/.bin/next dev --turbopack 2>&1 | tee -a ../../logs/web.log
