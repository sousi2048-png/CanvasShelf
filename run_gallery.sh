#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PORT="${1:-8765}"
exec uv run --no-project python "$SCRIPT_DIR/server.py" --host 127.0.0.1 --port "$PORT" --open
