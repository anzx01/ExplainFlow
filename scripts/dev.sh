#!/usr/bin/env bash
# 一键启动全部开发服务（需要 tmux 或分别运行）
set -euo pipefail

SCRIPT_DIR="$(dirname "$0")"

echo "ExplainFlow 开发环境启动"
echo "========================================"
echo "  API:    http://localhost:8000"
echo "  Web:    http://localhost:3000"
echo "  Render: http://localhost:3001 (可选)"
echo "========================================"
echo ""
echo "请在不同终端分别运行："
echo "  bash scripts/dev-api.sh"
echo "  bash scripts/dev-web.sh"
echo "  bash scripts/dev-render.sh  (可选)"
