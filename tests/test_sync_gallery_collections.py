import tempfile
import unittest
from pathlib import Path

from CanvasShelf import sync_gallery_collections as sync


class GalleryCollectionSyncTests(unittest.TestCase):
    def test_discovers_image_directory_and_skips_existing_path(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            arts_dir = root / "Arts"
            new_directory = arts_dir / "参考画像"
            new_directory.mkdir(parents=True)
            (new_directory / "sample.jpg").write_bytes(b"image")
            config = {"collections": [{"id": "existing", "path": str(new_directory)}]}
            self.assertEqual(sync.discover_new_collections(arts_dir, config), [])

            config = {"collections": []}
            additions = sync.discover_new_collections(arts_dir, config)
            self.assertEqual(len(additions), 1)
            self.assertEqual(additions[0]["label"], "参考画像")
            self.assertTrue(additions[0]["id"].startswith("collection-"))

    def test_ignores_directory_without_supported_images(self):
        with tempfile.TemporaryDirectory() as directory_name:
            arts_dir = Path(directory_name) / "Arts"
            (arts_dir / "empty").mkdir(parents=True)
            (arts_dir / "notes").mkdir()
            (arts_dir / "notes" / "readme.txt").write_text("not an image", encoding="utf-8")
            self.assertEqual(sync.discover_new_collections(arts_dir, {"collections": []}), [])

    def test_discovered_directories_are_returned_for_append_after_existing_items(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            arts_dir = root / "Arts"
            existing_directory = arts_dir / "Existing"
            new_directory = arts_dir / "New"
            existing_directory.mkdir(parents=True)
            new_directory.mkdir()
            (new_directory / "sample.jpg").write_bytes(b"image")
            config = {
                "collections": [
                    {"id": "existing", "label": "Existing", "path": str(existing_directory)},
                ]
            }
            additions = sync.discover_new_collections(arts_dir, config)
            self.assertEqual([item["label"] for item in additions], ["New"])
            config["collections"].extend(additions)
            self.assertEqual([item["label"] for item in config["collections"]], ["Existing", "New"])

    def test_config_base_controls_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            config_base = root / "app-data"
            arts_dir = root / "Arts"
            new_directory = arts_dir / "New"
            new_directory.mkdir(parents=True)
            (new_directory / "sample.jpg").write_bytes(b"image")

            additions = sync.discover_new_collections(
                arts_dir,
                {"collections": []},
                config_base=config_base,
            )

            self.assertEqual(additions[0]["path"], "../Arts/New")


if __name__ == "__main__":
    unittest.main()
