#!/usr/bin/env python3
"""共有Arts/配下の画像フォルダをCanvasShelfの設定へ追記する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_ARTS_DIR = ROOT_DIR.parent / "Arts"
DEFAULT_CONFIG_PATH = ROOT_DIR / "gallery_collections.json"
IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ACCENTS = ("coral", "sage", "blue", "amber")


def resolve_path(path: Path, base: Path = ROOT_DIR) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = base / expanded
    return expanded.resolve()


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        return {"collections": []}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"設定ファイルを読み込めません: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("collections"), list):
        raise ValueError("設定ファイルの collections は配列で指定してください。")
    return payload


def contains_images(directory: Path) -> bool:
    try:
        entries = directory.iterdir()
    except OSError:
        return False
    for path in entries:
        if path.name.startswith(".") or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        try:
            if path.is_file():
                return True
        except OSError:
            continue
    return False


def make_id(name: str, existing_ids: set[str], path: Path) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    if not slug:
        digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
        slug = f"collection-{digest}"
    if not ID_PATTERN.fullmatch(slug):
        slug = "collection"
    candidate = slug
    number = 2
    while candidate in existing_ids:
        candidate = f"{slug}-{number}"
        number += 1
    return candidate


def relative_config_path(path: Path) -> str:
    return os.path.relpath(path, ROOT_DIR).replace(os.sep, "/")


def discover_new_collections(arts_dir: Path, config: Dict[str, Any]) -> List[Dict[str, str]]:
    existing_collections = config["collections"]
    existing_paths = set()
    existing_ids = set()
    for collection in existing_collections:
        if not isinstance(collection, dict):
            continue
        path_value = collection.get("path")
        if isinstance(path_value, str) and path_value.strip():
            existing_paths.add(resolve_path(Path(path_value)))
        collection_id = collection.get("id")
        if isinstance(collection_id, str):
            existing_ids.add(collection_id)

    try:
        directories = sorted((path for path in arts_dir.iterdir() if path.is_dir()), key=lambda path: path.name.casefold())
    except OSError as exc:
        raise ValueError(f"Arts ディレクトリを読み込めません: {exc}") from exc

    additions: List[Dict[str, str]] = []
    for directory in directories:
        resolved_directory = directory.resolve()
        if resolved_directory in existing_paths or not contains_images(directory):
            continue
        collection_id = make_id(directory.name, existing_ids, resolved_directory)
        additions.append(
            {
                "id": collection_id,
                "label": directory.name,
                "path": relative_config_path(resolved_directory),
                "description": f"{directory.name} のローカル画像",
                "accent": ACCENTS[(len(existing_collections) + len(additions)) % len(ACCENTS)],
            }
        )
        existing_ids.add(collection_id)
        existing_paths.add(resolved_directory)
    return additions


def write_config(config_path: Path, config: Dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(config, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, config_path)
    except OSError as exc:
        raise ValueError(f"設定ファイルを書き込めません: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="共有Arts/配下の画像フォルダをCanvasShelfへ追記します。")
    parser.add_argument("--arts-dir", type=Path, default=DEFAULT_ARTS_DIR, help="走査するArtsディレクトリ")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="更新する設定ファイル")
    parser.add_argument("--dry-run", action="store_true", help="変更せず、追加予定だけ表示")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    arts_dir = resolve_path(args.arts_dir)
    config_path = resolve_path(args.config)
    try:
        config = load_config(config_path)
        additions = discover_new_collections(arts_dir, config)
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    if not additions:
        print(f"新しい画像フォルダはありません（走査先: {arts_dir}）。")
        return 0

    print(f"追加対象: {len(additions)}フォルダ")
    for collection in additions:
        print(f"  + {collection['label']} → /{collection['id']}")
    if args.dry_run:
        print("dry-run のため設定ファイルは変更していません。")
        return 0

    config["collections"].extend(additions)
    try:
        write_config(config_path, config)
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    print(f"設定を更新しました: {config_path}")
    print("ギャラリーを表示中の場合は、ページを再読み込みしてください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
