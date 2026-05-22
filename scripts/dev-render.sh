#!/usr/bin/env bash
# Start the Remotion render server (HTTP render service on port 3001).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT/apps/render"

if [ ! -d "node_modules" ]; then
  echo "[info] Installing Remotion dependencies..."
  npm install
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  echo "[warn] apps/render/.env not found, copying from .env.example"
  cp .env.example .env
fi

mkdir -p "$ROOT/outputs"
mkdir -p "$ROOT/logs"

# Browser discovery is automatic across Playwright, Chrome, Chromium, and Edge.
# To override it, set REMOTION_BROWSER_EXECUTABLE or REMOTION_CHROME_HEADLESS_SHELL
# in apps/render/.env or your shell environment.
# First-time setup, if no browser is installed: cd apps/render && npx playwright install chromium

echo "[info] Starting Render Server on http://localhost:3001 ..."
node server.mjs 2>&1 | tee -a "$ROOT/logs/render.log"
