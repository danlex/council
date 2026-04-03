#!/usr/bin/env bash
# Council of LLM CLIs — quick launcher
# Usage: ./c "Your question here"
#        ./c -v "Your question here"    (verbose)
#        ./c -p "Your question here"    (parallel via tmux)
#        ./c quick "Your question here" (no review, fast)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate" 2>/dev/null

if [ "$1" = "quick" ]; then
    shift
    council quick "$@"
elif [ "$1" = "models" ]; then
    council models
elif [ "$1" = "config" ]; then
    shift
    council config "$@"
else
    council ask "$@"
fi
