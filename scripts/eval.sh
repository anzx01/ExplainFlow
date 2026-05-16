#!/usr/bin/env bash
# 运行 ExplainFlow 评测（需要 services/api/.env 配置好 API key）
set -euo pipefail

cd "$(dirname "$0")/../services/api"

if [ ! -f ".env" ]; then
  echo "[error] services/api/.env not found. Please copy .env.example and fill in your API key."
  exit 1
fi

echo "[info] Running ExplainFlow evals..."
uv run python ../../evals/run_eval.py "$@"
