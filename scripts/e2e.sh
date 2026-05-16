#!/usr/bin/env bash
# ExplainFlow E2E 测试
# 覆盖：ExplainGraph → Storyboard（含 image_description）→ Imagegen（Seedream API）
#
# 用法：
#   bash scripts/e2e.sh                        # 完整 e2e（含真实图像生成 API）
#   bash scripts/e2e.sh --skip-imagegen        # 跳过图像生成（只测 LLM 链路）
#   bash scripts/e2e.sh --topic 梯度下降       # 只跑单题
set -euo pipefail

cd "$(dirname "$0")/../services/api"

if [ ! -f ".env" ]; then
  echo "[error] services/api/.env not found. Please copy .env.example and fill in your API keys."
  exit 1
fi

echo "[e2e] Running ExplainFlow E2E tests..."
uv run python ../../evals/e2e_test.py "$@"
