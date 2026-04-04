#!/usr/bin/env bash
# Council of LLM CLIs
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Setting up council..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    "$SCRIPT_DIR/.venv/bin/pip" install -e "$SCRIPT_DIR" -q
fi

source "$SCRIPT_DIR/.venv/bin/activate"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi
exec python3 -m council.cli
