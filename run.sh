#!/usr/bin/env bash
set -euo pipefail

# One-click runner for the agent on macOS
# - Creates venv if missing
# - Installs dependencies and playwright chromium (first run)
# - Loads .env via python-dotenv (executor does this), but we also source it if present for convenience
# - Starts the agent

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

cd "$ROOT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[setup] creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

if [[ -f "$ROOT_DIR/.env" ]]; then
  echo "[env] loading .env"
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
fi

echo "[deps] installing requirements"
"$PIP" install -r "$ROOT_DIR/requirements.txt"

echo "[playwright] ensuring chromium is installed"
"$PY" -m playwright install chromium

echo "[run] launching agent"
"$PY" "$ROOT_DIR/main.py"
