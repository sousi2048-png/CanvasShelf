#!/usr/bin/env python3
"""CanvasShelf: local masonry image viewer for configurable image collections."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, quote, unquote, urlsplit

try:
    from .sync_gallery_collections import (
        discover_new_collections,
        load_config as load_sync_config,
        make_id,
        write_config as write_sync_config,
    )
except ImportError:  # スクリプトとして直接起動した場合
    from sync_gallery_collections import (
        discover_new_collections,
        load_config as load_sync_config,
        make_id,
        write_config as write_sync_config,
    )


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ROOT_DIR.parent
STATIC_DIR = ROOT_DIR / "gallery"
COLLECTION_CONFIG_PATH = ROOT_DIR / "gallery_collections.json"
ARTS_DIR = PROJECT_DIR / "Arts"
PREFERENCES_PATH = ROOT_DIR / ".gallery_preferences.json"
TRASH_DIR = Path.home() / ".Trash"
SYNC_LOCK = threading.Lock()
COLLECTIONS_LOCK = threading.Lock()
PREFERENCES_LOCK = threading.Lock()
DELETE_LOCK = threading.Lock()
DEFAULT_COLLECTIONS = [
    {"id": "Collection", "label": "Collection", "path": "../Arts/Collection", "description": "日常のひらめきと、あとで見返したい画像", "accent": "coral"},
    {"id": "Collection 2", "label": "Collection 2", "path": "../Arts/Collection 2", "description": "別にまとめておきたい、もうひとつのコレクション", "accent": "sage"},
]
COLLECTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
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
MEMO_FILENAME = "memo.md"
MAX_MEMO_SIZE = 512 * 1024
SORT_VALUES = {"newest", "oldest", "name"}
MAX_REQUEST_SIZE = 64 * 1024


class CollectionConfigError(ValueError):
    """画像コレクション設定が不正な場合に使う例外。"""


def load_collections() -> List[Dict[str, object]]:
    """設定ファイルを読み込み、相対パスをプロジェクト基準へ解決する。

    サーバー起動後に設定ファイルを編集しても、次回のAPIリクエストから反映される。
    """
    try:
        if COLLECTION_CONFIG_PATH.exists():
            payload = json.loads(COLLECTION_CONFIG_PATH.read_text(encoding="utf-8"))
        else:
            payload = {"collections": DEFAULT_COLLECTIONS}
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectionConfigError(f"コレクション設定を読み込めません: {exc}") from exc

    raw_collections = payload.get("collections") if isinstance(payload, dict) else None
    if not isinstance(raw_collections, list):
        raise CollectionConfigError("collections は配列で指定してください。")

    collections: List[Dict[str, object]] = []
    seen_ids = set()
    for index, raw in enumerate(raw_collections, start=1):
        if not isinstance(raw, dict):
            raise CollectionConfigError(f"collections[{index}] はオブジェクトで指定してください。")
        collection_id = str(raw.get("id", "")).strip()
        label = str(raw.get("label", collection_id)).strip()
        path_text = str(raw.get("path", "")).strip()
        if not COLLECTION_ID_PATTERN.fullmatch(collection_id):
            raise CollectionConfigError(f"collections[{index}].id は英数字・ハイフン・アンダースコアのみ使えます。")
        if collection_id in seen_ids:
            raise CollectionConfigError(f"コレクションIDが重複しています: {collection_id}")
        if not label or not path_text:
            raise CollectionConfigError(f"collections[{index}] には label と path が必要です。")
        resolved_path = resolve_collection_path(path_text)
        if not resolved_path.is_dir():
            continue
        collections.append(
            {
                "id": collection_id,
                "label": label,
                "path": resolved_path,
                "description": str(raw.get("description", "ローカル画像コレクション")).strip(),
                "accent": str(raw.get("accent", "coral")).strip() or "coral",
            }
        )
        seen_ids.add(collection_id)
    return collections


def resolve_collection_path(path_text: str) -> Path:
    """設定ファイルのパスをCanvasShelf基準で解決する。"""
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def relative_config_path(path: Path) -> str:
    """CanvasShelf基準の相対パスへ変換する。"""
    return os.path.relpath(path.resolve(), ROOT_DIR).replace(os.sep, "/")


def load_raw_collection_config() -> Dict[str, object]:
    """欠落フォルダを含む設定を、編集用に読み込む。"""
    payload = load_sync_config(COLLECTION_CONFIG_PATH)
    if not isinstance(payload.get("collections"), list):
        raise CollectionConfigError("collections は配列で指定してください。")
    return payload


def add_collection(path_text: str) -> Dict[str, str]:
    """閲覧対象としてフォルダを登録する（実ファイルは変更しない）。"""
    if not isinstance(path_text, str) or not path_text.strip():
        raise ValueError("フォルダのパスが必要です。")
    resolved_path = resolve_collection_path(path_text.strip())
    if not resolved_path.is_dir():
        raise FileNotFoundError("指定したフォルダが見つかりません。")

    with COLLECTIONS_LOCK:
        config = load_raw_collection_config()
        raw_collections = config["collections"]
        existing_ids = set()
        for raw in raw_collections:
            if not isinstance(raw, dict):
                continue
            collection_id = raw.get("id")
            if isinstance(collection_id, str):
                existing_ids.add(collection_id)
            configured_path = raw.get("path")
            if isinstance(configured_path, str) and configured_path.strip():
                if resolve_collection_path(configured_path) == resolved_path:
                    raise FileExistsError("このフォルダはすでに登録されています。")

        collection_id = make_id(resolved_path.name, existing_ids, resolved_path)
        collection = {
            "id": collection_id,
            "label": resolved_path.name or str(resolved_path),
            "path": relative_config_path(resolved_path),
            "description": f"{resolved_path.name or '選択したフォルダ'} のローカル画像",
            "accent": ("coral", "sage", "blue", "amber")[len(raw_collections) % 4],
        }
        raw_collections.append(collection)
        write_sync_config(COLLECTION_CONFIG_PATH, config)
        return collection


def remove_collection(collection_id: str) -> Dict[str, str]:
    """閲覧対象の登録だけを削除する（実フォルダ・画像は削除しない）。"""
    if not isinstance(collection_id, str) or not COLLECTION_ID_PATTERN.fullmatch(collection_id):
        raise ValueError("コレクションIDが不正です。")
    with COLLECTIONS_LOCK:
        config = load_raw_collection_config()
        raw_collections = config["collections"]
        for index, raw in enumerate(raw_collections):
            if isinstance(raw, dict) and raw.get("id") == collection_id:
                removed = dict(raw)
                raw_collections.pop(index)
                write_sync_config(COLLECTION_CONFIG_PATH, config)
                return {
                    "id": collection_id,
                    "label": str(removed.get("label", collection_id)),
                    "path": str(removed.get("path", "")),
                }
    raise KeyError("Unknown collection")


def pick_folder_with_os_dialog() -> Path:
    """OS標準のフォルダ選択ダイアログを開き、選択結果を返す。"""
    if sys.platform == "darwin":
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "CanvasShelfで閲覧するフォルダを選択")',
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            raise InterruptedError("フォルダ選択をキャンセルしました。")
        selected = result.stdout.strip()
    elif os.name == "nt":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "if ($dialog.ShowDialog() -eq 'OK') { [Console]::WriteLine($dialog.SelectedPath) }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            raise InterruptedError("フォルダ選択をキャンセルしました。")
        selected = result.stdout.strip()
    else:
        for command in ("zenity", "kdialog"):
            if shutil.which(command) is None:
                continue
            args = [command, "--file-selection", "--directory"] if command == "zenity" else [command, "--getexistingdirectory"]
            result = subprocess.run(args, capture_output=True, text=True, timeout=300, check=False)
            if result.returncode != 0:
                raise InterruptedError("フォルダ選択をキャンセルしました。")
            selected = result.stdout.strip()
            break
        else:
            raise RuntimeError("フォルダ選択ダイアログを利用できません。パスを直接入力してください。")

    if not selected:
        raise InterruptedError("フォルダ選択をキャンセルしました。")
    selected_path = Path(selected).expanduser().resolve()
    if not selected_path.is_dir():
        raise FileNotFoundError("選択したフォルダが見つかりません。")
    return selected_path


def collection_map(collections: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    return {str(collection["id"]): collection for collection in collections}


def is_safe_child(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath((str(path.resolve()), str(parent.resolve()))) == str(parent.resolve())
    except (OSError, ValueError):
        return False


def list_images(collection: Dict[str, object]) -> List[Dict[str, object]]:
    collection_id = str(collection["id"])
    directory = collection["path"]
    if not isinstance(directory, Path) or not directory.is_dir():
        return []
    images: List[Dict[str, object]] = []
    try:
        entries = directory.iterdir()
    except OSError:
        return []
    for path in entries:
        if path.name.startswith(".") or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if not path.is_file() or not is_safe_child(path, directory):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        images.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "modifiedIso": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "url": f"/media/{quote(collection_id)}/{quote(path.name)}",
            }
        )
    return sorted(images, key=lambda image: float(image["modified"]), reverse=True)


def _next_trash_path(filename: str, trash_dir: Path) -> Path:
    """ゴミ箱内で既存ファイルを上書きしない移動先を返す。"""
    original = trash_dir / filename
    if not original.exists() and not original.is_symlink():
        return original

    source = Path(filename)
    stem = source.stem or "image"
    suffix = source.suffix
    counter = 2
    while True:
        candidate = trash_dir / f"{stem} {counter}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        counter += 1


def move_image_to_trash(collection: Dict[str, object], filename: str) -> Path:
    """コレクション内の画像をmacOSのゴミ箱へ移動する。"""
    if not isinstance(filename, str) or not filename or filename in {".", ".."}:
        raise ValueError("画像名が不正です。")
    if Path(filename).name != filename:
        raise ValueError("画像名が不正です。")

    directory = collection.get("path")
    if not isinstance(directory, Path) or not directory.is_dir():
        raise FileNotFoundError("画像フォルダが見つかりません。")

    # 削除確認と移動を同じロックで囲み、複数タブからの同時操作を直列化する。
    with DELETE_LOCK:
        source = directory / filename
        try:
            resolved_source = source.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise FileNotFoundError("画像が見つかりません。") from exc
        if (
            not is_safe_child(resolved_source, directory)
            or resolved_source.suffix.lower() not in IMAGE_EXTENSIONS
            or not resolved_source.is_file()
        ):
            raise FileNotFoundError("画像が見つかりません。")

        trash_dir = TRASH_DIR.expanduser()
        try:
            trash_dir.mkdir(parents=True, exist_ok=True)
            destination = _next_trash_path(resolved_source.name, trash_dir)
            shutil.move(str(resolved_source), str(destination))
        except FileNotFoundError as exc:
            raise FileNotFoundError("画像が見つかりません。") from exc
        except OSError as exc:
            raise OSError("ゴミ箱へ移動できませんでした。") from exc
    return destination


def read_memo(collection: Dict[str, object]) -> str:
    """コレクション直下のmemo.mdを安全に読み込む。"""
    directory = collection.get("path")
    if not isinstance(directory, Path) or not directory.is_dir():
        return ""
    memo_path = directory / MEMO_FILENAME
    if not is_safe_child(memo_path, directory) or not memo_path.is_file():
        return ""
    try:
        return memo_path.read_text(encoding="utf-8-sig")[:MAX_MEMO_SIZE].strip()
    except (OSError, UnicodeError):
        return ""


def load_sort_preferences() -> Dict[str, str]:
    """フォルダ別の並び順を読み込む。壊れた保存値は無視する。"""
    try:
        payload = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    raw_preferences = payload.get("sort") if isinstance(payload, dict) else None
    if not isinstance(raw_preferences, dict):
        return {}
    return {
        str(collection_id): str(value)
        for collection_id, value in raw_preferences.items()
        if str(value) in SORT_VALUES
    }


def save_sort_preference(collection_id: str, value: str) -> None:
    """フォルダ別の並び順を原子的に保存する。"""
    if not COLLECTION_ID_PATTERN.fullmatch(collection_id) or value not in SORT_VALUES:
        raise ValueError("並び順の保存値が不正です。")
    with PREFERENCES_LOCK:
        preferences = load_sort_preferences()
        preferences[collection_id] = value
        payload = {"sort": preferences}
        temporary_path = None
        try:
            PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=PREFERENCES_PATH.parent,
                prefix=f".{PREFERENCES_PATH.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, PREFERENCES_PATH)
        except OSError as exc:
            raise ValueError(f"並び順を保存できません: {exc}") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)


def sync_collections() -> List[Dict[str, str]]:
    """Arts/を走査し、新しい画像フォルダを設定へ追記する。"""
    with SYNC_LOCK:
        config = load_sync_config(COLLECTION_CONFIG_PATH)
        additions = discover_new_collections(ARTS_DIR, config)
        if additions:
            config["collections"].extend(additions)
            write_sync_config(COLLECTION_CONFIG_PATH, config)
        return additions


class GalleryHandler(SimpleHTTPRequestHandler):
    server_version = "CanvasShelf/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        static_path = urlsplit(self.path).path
        if static_path in {"/index.html", "/app.js", "/styles.css"}:
            self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
        )
        super().end_headers()

    def send_head(self):  # noqa: ANN001
        # ローカル開発中に更新したJS/CSS/HTMLが304キャッシュで残らないようにする。
        static_path = urlsplit(self.path).path
        if static_path in {"/", "/index.html", "/app.js", "/styles.css"}:
            if "If-Modified-Since" in self.headers:
                del self.headers["If-Modified-Since"]
            if "If-None-Match" in self.headers:
                del self.headers["If-None-Match"]
        return super().send_head()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        route = unquote(parsed.path)

        try:
            collections = load_collections()
        except CollectionConfigError as exc:
            if route.startswith("/api/"):
                self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        by_id = collection_map(collections)

        if route == "/health":
            self.send_json({"ok": True})
            return

        if route == "/api/collections":
            sort_preferences = load_sort_preferences()
            public = []
            for collection in collections:
                images = list_images(collection)
                public.append(
                    {
                        "id": collection["id"],
                        "label": collection["label"],
                        "description": collection["description"],
                        "accent": collection["accent"],
                        "count": len(images),
                        "previews": images[:3],
                        "sort": sort_preferences.get(str(collection["id"]), "newest"),
                    }
                )
            self.send_json({"collections": public})
            return

        if route == "/api/images":
            params = parse_qs(parsed.query)
            collection_id = params.get("collection", params.get("folder", [""]))[0]
            collection = by_id.get(collection_id)
            if collection is None:
                self.send_json({"error": "Unknown collection"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json(
                {
                    "collection": collection_id,
                    "images": list_images(collection),
                    "memo": read_memo(collection),
                }
            )
            return

        if route.startswith("/media/"):
            self.serve_media(route, by_id)
            return

        route_parts = [part for part in route.split("/") if part]
        # コレクションIDらしい単一セグメントは、設定から消えた古いURLも
        # アプリに渡してトップページへ戻せるようにする。
        if route == "/" or (len(route_parts) == 1 and COLLECTION_ID_PATTERN.fullmatch(route_parts[0])):
            self.path = "/index.html"
        else:
            self.path = route
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        route = unquote(parsed.path)
        if route == "/api/collections/add":
            self.add_collection()
            return
        if route == "/api/collections/remove":
            self.remove_collection()
            return
        if route == "/api/pick-folder":
            self.pick_folder()
            return
        if route == "/api/images/delete":
            self.delete_image()
            return
        if route == "/api/preferences/sort":
            self.update_sort_preference()
            return
        if route != "/api/sync-collections":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            additions = sync_collections()
        except (OSError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self.send_json(
            {
                "added": [{"id": item["id"], "label": item["label"]} for item in additions],
                "addedCount": len(additions),
            }
        )

    def read_json_body(self, max_size: int = MAX_REQUEST_SIZE) -> object:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("リクエストが不正です。") from exc
        if content_length <= 0 or content_length > max_size:
            raise ValueError("リクエストが不正です。")
        try:
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("リクエストが不正です。") from exc

    def add_collection(self) -> None:
        try:
            payload = self.read_json_body()
            path_text = payload.get("path") if isinstance(payload, dict) else None
            collection = add_collection(path_text)
        except FileExistsError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except FileNotFoundError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        except (CollectionConfigError, OSError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.send_json({"added": collection}, HTTPStatus.CREATED)

    def remove_collection(self) -> None:
        try:
            payload = self.read_json_body()
            collection_id = payload.get("collection") if isinstance(payload, dict) else None
            removed = remove_collection(collection_id)
        except KeyError:
            self.send_json({"error": "Unknown collection"}, HTTPStatus.NOT_FOUND)
            return
        except (CollectionConfigError, OSError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.send_json({"removed": removed})

    def pick_folder(self) -> None:
        try:
            selected_path = pick_folder_with_os_dialog()
        except InterruptedError as exc:
            self.send_json({"cancelled": True, "error": str(exc)}, HTTPStatus.OK)
            return
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.send_json(
            {
                "path": relative_config_path(selected_path),
                "label": selected_path.name or str(selected_path),
            }
        )

    def update_sort_preference(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json({"error": "リクエストが不正です。"}, HTTPStatus.BAD_REQUEST)
            return
        if content_length <= 0 or content_length > 8192:
            self.send_json({"error": "リクエストが不正です。"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            self.send_json({"error": "リクエストが不正です。"}, HTTPStatus.BAD_REQUEST)
            return
        collection_id = payload.get("collection") if isinstance(payload, dict) else None
        value = payload.get("sort") if isinstance(payload, dict) else None
        if not isinstance(collection_id, str) or not isinstance(value, str):
            self.send_json({"error": "コレクションと並び順が必要です。"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            collections = collection_map(load_collections())
        except CollectionConfigError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if collection_id not in collections:
            self.send_json({"error": "Unknown collection"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            save_sort_preference(collection_id, value)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.send_json({"collection": collection_id, "sort": value})

    def delete_image(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json({"error": "リクエストが不正です。"}, HTTPStatus.BAD_REQUEST)
            return
        if content_length <= 0 or content_length > 8192:
            self.send_json({"error": "リクエストが不正です。"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            self.send_json({"error": "リクエストが不正です。"}, HTTPStatus.BAD_REQUEST)
            return

        collection_id = payload.get("collection") if isinstance(payload, dict) else None
        filename = payload.get("filename") if isinstance(payload, dict) else None
        if not isinstance(collection_id, str) or not isinstance(filename, str):
            self.send_json({"error": "コレクションとファイル名が必要です。"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            collections = collection_map(load_collections())
        except CollectionConfigError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        collection = collections.get(collection_id)
        if collection is None:
            self.send_json({"error": "Unknown collection"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            destination = move_image_to_trash(collection, filename)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except FileNotFoundError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        except OSError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_json(
            {
                "deleted": True,
                "collection": collection_id,
                "filename": filename,
                "trashName": destination.name,
            }
        )

    def send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_media(self, route: str, collections: Dict[str, Dict[str, object]]) -> None:
        pieces = route.split("/", 3)
        if len(pieces) != 4:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        collection_id, filename = pieces[2], pieces[3]
        collection = collections.get(collection_id)
        if collection is None or not filename:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        directory = collection["path"]
        if not isinstance(directory, Path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        candidate = (directory / unquote(filename)).resolve()
        if (
            candidate.suffix.lower() not in IMAGE_EXTENSIONS
            or not is_safe_child(candidate, directory)
            or not candidate.is_file()
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            payload = candidate.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the configured local image gallery.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--open", action="store_true", help="Open the gallery in the default browser")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), GalleryHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"CanvasShelf gallery: {url}", flush=True)
    if args.open:
        try:
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            print("ブラウザを自動で開けませんでした。上のURLを開いてください。", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGallery stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
