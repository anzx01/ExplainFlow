#!/usr/bin/env bash
# 启动 FastAPI 后端开发服务器
set -euo pipefail

cd "$(dirname "$0")/../services/api"

if [ ! -f ".env" ]; then
  echo "[warn] .env not found, copying from .env.example"
  cp .env.example .env
fi

echo "[info] Starting FastAPI dev server on http://localhost:8000 ..."
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee -a ../../logs/api.log
