#!/usr/bin/env bash
# 初始化项目依赖（首次运行）
set -euo pipefail

ROOT="$(dirname "$0")/.."

echo "[1/4] 配置环境变量..."
if [ ! -f "$ROOT/services/api/.env" ]; then
  cp "$ROOT/services/api/.env.example" "$ROOT/services/api/.env"
  echo "  已创建 services/api/.env，请填写 OPENAI_API_KEY"
fi
if [ ! -f "$ROOT/apps/web/.env.local" ]; then
  cp "$ROOT/apps/web/.env.local.example" "$ROOT/apps/web/.env.local"
  echo "  已创建 apps/web/.env.local"
fi

echo "[2/4] 安装 Python 依赖..."
cd "$ROOT/services/api"
uv sync

echo "[3/4] 安装 Web 前端依赖..."
cd "$ROOT/apps/web"
npm install

echo "[4/4] 创建日志目录..."
mkdir -p "$ROOT/logs"

echo ""
echo "✓ 初始化完成！请编辑 services/api/.env，填写你的 DeepSeek API Key"
echo "  然后运行 bash scripts/dev-api.sh 和 bash scripts/dev-web.sh"
