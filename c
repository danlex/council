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
exec python3 -m council.cli
