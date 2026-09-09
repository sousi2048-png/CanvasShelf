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
            (directory / "memo.md").write_text("# メモ\n\n本文です。", encoding="utf-8")
            memo = server.read_memo({"path": directory})
            self.assertEqual(memo, "# メモ\n\n本文です。")

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

    def test_sort_preference_is_saved_per_collection(self):
        with tempfile.TemporaryDirectory() as directory_name:
            preferences_path = Path(directory_name) / ".gallery_preferences.json"
            with patch.object(server, "PREFERENCES_PATH", preferences_path):
                server.save_sort_preference("photos", "name")
                server.save_sort_preference("other", "oldest")
                preferences = server.load_sort_preferences()
            self.assertEqual(preferences, {"photos": "name", "other": "oldest"})

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
