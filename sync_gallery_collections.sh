#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
exec uv run --no-project python "$SCRIPT_DIR/sync_gallery_collections.py" "$@"
