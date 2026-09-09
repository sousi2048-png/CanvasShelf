import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from CanvasShelf import server


class GalleryConfigTests(unittest.TestCase):
    def test_loads_relative_and_absolute_collection_paths(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            image_dir = root / "images"
            image_dir.mkdir()
            config_path = root / "collections.json"
            config_path.write_text(
                json.dumps(
                    {
                        "collections": [
                            {"id": "local", "label": "Local", "path": "images"},
                            {"id": "external", "label": "External", "path": str(image_dir)},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(server, "ROOT_DIR", root), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                collections = server.load_collections()
            self.assertEqual([item["id"] for item in collections], ["local", "external"])
            self.assertEqual(collections[0]["path"], image_dir.resolve())
            self.assertEqual(collections[1]["path"], image_dir.resolve())

    def test_rejects_unsafe_collection_id(self):
        with tempfile.TemporaryDirectory() as directory_name:
            config_path = Path(directory_name) / "collections.json"
            config_path.write_text(
                '{"collections":[{"id":"../private","label":"Bad","path":"images"}]}',
                encoding="utf-8",
            )
            with patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                with self.assertRaises(server.CollectionConfigError):
                    server.load_collections()

    def test_omits_collections_whose_directory_is_gone(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            existing = root / "existing"
            existing.mkdir()
            config_path = root / "collections.json"
            config_path.write_text(
                json.dumps(
                    {
                        "collections": [
                            {"id": "existing", "path": str(existing)},
                            {"id": "gone", "path": str(root / "gone")},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                collections = server.load_collections()
            self.assertEqual([item["id"] for item in collections], ["existing"])

    def test_reads_memo_from_collection_root(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            (directory / "memo.md").write_text("\n# メモ\n\n本文です。\n", encoding="utf-8")
            memo = server.read_memo({"path": directory})
            self.assertEqual(memo, "\n# メモ\n\n本文です。\n")

    def test_writes_memo_and_creates_file_atomically(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            collection = {"path": directory}
            saved = server.write_memo(collection, "# 新しいメモ\r\n\r\n本文です。")
            self.assertEqual(saved, "# 新しいメモ\n\n本文です。")
            self.assertEqual((directory / "memo.md").read_text(encoding="utf-8"), saved)
            self.assertEqual(server.read_memo(collection), saved)

            server.write_memo(collection, "")
            self.assertTrue((directory / "memo.md").is_file())
            self.assertEqual((directory / "memo.md").read_text(encoding="utf-8"), "")

    def test_rejects_memo_larger_than_limit(self):
        with tempfile.TemporaryDirectory() as directory_name:
            with self.assertRaises(ValueError):
                server.write_memo({"path": Path(directory_name)}, "あ" * (server.MAX_MEMO_SIZE // 2 + 1))

    def test_sync_collections_appends_new_image_directory_once(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            arts_dir = root / "Arts"
            new_directory = arts_dir / "New Folder"
            new_directory.mkdir(parents=True)
            (new_directory / "sample.jpg").write_bytes(b"image")
            config_path = root / "collections.json"
            config_path.write_text('{"collections": []}', encoding="utf-8")

            with patch.object(server, "ARTS_DIR", arts_dir), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                additions = server.sync_collections()
                repeated_additions = server.sync_collections()

            self.assertEqual([item["label"] for item in additions], ["New Folder"])
            self.assertEqual(repeated_additions, [])
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["collections"]), 1)
            self.assertEqual(saved["collections"][0]["id"], "new-folder")

    def test_sync_collections_keeps_existing_order_and_appends_new_items(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            arts_dir = root / "Arts"
            existing_directory = arts_dir / "Existing"
            new_directory = arts_dir / "New"
            existing_directory.mkdir(parents=True)
            new_directory.mkdir()
            (existing_directory / "existing.jpg").write_bytes(b"existing")
            (new_directory / "new.jpg").write_bytes(b"new")
            config_path = root / "collections.json"
            config_path.write_text(
                json.dumps(
                    {
                        "collections": [
                            {"id": "existing", "label": "Existing", "path": str(existing_directory)},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(server, "ARTS_DIR", arts_dir), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                additions = server.sync_collections()

            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual([item["label"] for item in additions], ["New"])
            self.assertEqual([item["label"] for item in saved["collections"]], ["Existing", "New"])

    def test_add_collection_persists_relative_path_without_touching_folder(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name).resolve()
            selected = root / "Selected Images"
            selected.mkdir()
            config_path = root / "collections.json"
            config_path.write_text('{"collections": []}', encoding="utf-8")
            with patch.object(server, "ROOT_DIR", root), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                added = server.add_collection("Selected Images")
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(added["label"], "Selected Images")
            self.assertEqual(saved["collections"][0]["path"], "Selected Images")
            self.assertTrue(selected.is_dir())

    def test_add_collection_rejects_duplicate_path(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            selected = root / "selected"
            selected.mkdir()
            config_path = root / "collections.json"
            config_path.write_text(
                json.dumps({"collections": [{"id": "selected", "label": "selected", "path": "selected"}]}),
                encoding="utf-8",
            )
            with patch.object(server, "ROOT_DIR", root), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                with self.assertRaises(FileExistsError):
                    server.add_collection("selected")

    def test_remove_collection_only_updates_config(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            selected = root / "selected"
            selected.mkdir()
            config_path = root / "collections.json"
            config_path.write_text(
                json.dumps({"collections": [{"id": "selected", "label": "Selected", "path": "selected"}]}),
                encoding="utf-8",
            )
            with patch.object(server, "ROOT_DIR", root), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                removed = server.remove_collection("selected")
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(removed["id"], "selected")
            self.assertEqual(saved["collections"], [])
            self.assertTrue(selected.is_dir())

    def test_reorder_collections_persists_visible_order_and_keeps_missing_entry(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            config_path = root / "collections.json"
            config_path.write_text(
                json.dumps(
                    {
                        "collections": [
                            {"id": "first", "label": "First", "path": "first"},
                            {"id": "gone", "label": "Gone", "path": "missing"},
                            {"id": "second", "label": "Second", "path": "second"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(server, "ROOT_DIR", root), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                saved_order = server.reorder_collections(["second", "first"])
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_order, ["second", "first"])
            self.assertEqual([item["id"] for item in saved["collections"]], ["second", "gone", "first"])

    def test_reorder_collections_requires_all_visible_ids(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            (root / "first").mkdir()
            (root / "second").mkdir()
            config_path = root / "collections.json"
            config_path.write_text(
                json.dumps(
                    {
                        "collections": [
                            {"id": "first", "label": "First", "path": "first"},
                            {"id": "second", "label": "Second", "path": "second"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(server, "ROOT_DIR", root), patch.object(server, "COLLECTION_CONFIG_PATH", config_path):
                with self.assertRaises(ValueError):
                    server.reorder_collections(["first"])

    def test_sort_preference_is_saved_per_collection(self):
        with tempfile.TemporaryDirectory() as directory_name:
            preferences_path = Path(directory_name) / ".gallery_preferences.json"
            with patch.object(server, "PREFERENCES_PATH", preferences_path):
                server.save_sort_preference("photos", "name")
                server.save_sort_preference("other", "oldest")
                preferences = server.load_sort_preferences()
            self.assertEqual(preferences, {"photos": "name", "other": "oldest"})

    def test_home_sort_preference_is_saved_without_overwriting_image_sort(self):
        with tempfile.TemporaryDirectory() as directory_name:
            preferences_path = Path(directory_name) / ".gallery_preferences.json"
            with patch.object(server, "PREFERENCES_PATH", preferences_path):
                server.save_sort_preference("photos", "name")
                server.save_home_sort_preference("oldest")
                server.save_sort_preference("other", "newest")
                preferences = json.loads(preferences_path.read_text(encoding="utf-8"))
                home_sort = server.load_home_sort_preference()
            self.assertEqual(home_sort, "oldest")
            self.assertEqual(preferences["sort"], {"photos": "name", "other": "newest"})

    def test_moves_image_to_trash_without_overwriting_existing_file(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            collection_dir = root / "collection"
            trash_dir = root / "Trash"
            collection_dir.mkdir()
            trash_dir.mkdir()
            image = collection_dir / "sample.jpg"
            image.write_bytes(b"image")
            (trash_dir / "sample.jpg").write_bytes(b"older image")

            with patch.object(server, "TRASH_DIR", trash_dir):
                destination = server.move_image_to_trash({"path": collection_dir}, image.name)

            self.assertFalse(image.exists())
            self.assertEqual(destination, trash_dir / "sample 2.jpg")
            self.assertEqual(destination.read_bytes(), b"image")

    def test_rejects_image_path_when_moving_to_trash(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            with self.assertRaises(ValueError):
                server.move_image_to_trash({"path": directory}, "../outside.jpg")

    def test_list_images_ignores_hidden_and_non_image_files(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            (directory / "visible.jpg").write_bytes(b"image")
            (directory / ".hidden.jpg").write_bytes(b"hidden")
            (directory / "notes.txt").write_text("not an image", encoding="utf-8")
            images = server.list_images({"id": "sample", "path": directory})
            self.assertEqual([image["name"] for image in images], ["visible.jpg"])
            self.assertIn("/media/sample/visible.jpg", images[0]["url"])


if __name__ == "__main__":
    unittest.main()
