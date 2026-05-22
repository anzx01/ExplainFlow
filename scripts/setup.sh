#!/usr/bin/env bash
# First-time project setup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "[1/5] Creating local env files..."
if [ ! -f "$ROOT/services/api/.env" ]; then
  cp "$ROOT/services/api/.env.example" "$ROOT/services/api/.env"
  echo "  created services/api/.env; fill OPENAI_API_KEY before using LLM features"
fi
if [ ! -f "$ROOT/apps/web/.env.local" ]; then
  cp "$ROOT/apps/web/.env.local.example" "$ROOT/apps/web/.env.local"
  echo "  created apps/web/.env.local"
fi
if [ ! -f "$ROOT/apps/render/.env" ]; then
  cp "$ROOT/apps/render/.env.example" "$ROOT/apps/render/.env"
  echo "  created apps/render/.env; browser path can stay empty for auto discovery"
fi

echo "[2/5] Installing Python dependencies..."
cd "$ROOT/services/api"
uv sync

echo "[3/5] Installing web dependencies..."
cd "$ROOT/apps/web"
npm install

echo "[4/5] Installing render dependencies..."
cd "$ROOT/apps/render"
npm install

echo "[5/5] Creating runtime directories..."
mkdir -p "$ROOT/logs" "$ROOT/outputs"

echo ""
echo "Setup complete."
echo "Next: edit services/api/.env, then run scripts/dev-api.sh, scripts/dev-web.sh, and scripts/dev-render.sh."
