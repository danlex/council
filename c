#!/usr/bin/env bash
# Council of LLM CLIs
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate" 2>/dev/null
python3 -m council.cli
