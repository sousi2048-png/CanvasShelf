#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

for generated_dir in build dist release; do
  if [[ -e "$generated_dir" ]]; then
    rm -rf -- "$generated_dir"
  fi
done

# uvが管理するPython環境でPyInstallerを実行する（venvやpipは使わない）。
uv python install 3.12
uvx --python 3.12 --from 'pyinstaller==6.22.2' pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name CanvasShelf \
  --specpath build \
  --paths . \
  --hidden-import sync_gallery_collections \
  --add-data "$PROJECT_DIR/gallery:gallery" \
  server.py

if [[ ! -d "dist/CanvasShelf.app" ]]; then
  echo "CanvasShelf.app が作成されませんでした。" >&2
  exit 1
fi

mkdir -p release
case "$(uname -m)" in
  arm64) asset_suffix="apple-silicon" ;;
  x86_64) asset_suffix="intel" ;;
  *) asset_suffix="$(uname -m)" ;;
esac
ditto -c -k --sequesterRsrc --keepParent \
  "dist/CanvasShelf.app" \
  "release/CanvasShelf-macos-${asset_suffix}.zip"
echo "作成しました: release/CanvasShelf-macos-${asset_suffix}.zip"
