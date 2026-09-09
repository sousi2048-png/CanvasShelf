# CanvasShelf

CanvasShelf is a local-only image viewer. It presents images from folders you choose in a responsive masonry layout and opens them in a lightbox. The server listens on the local machine by default, so image files are not uploaded anywhere.

CanvasShelf is independent of the ShortcutSave browser extension. It does not require a particular folder layout: folders can be registered from the home page, while `../Arts/` is available as a convenient scan target when it exists next to this project.

## Requirements

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/)
- A modern browser

No third-party Python package is required. The scripts use `uv run --no-project` so the repository can be run without creating a virtual environment.

## Run

From the CanvasShelf directory:

```sh
./run_gallery.sh
```

The script starts the server on `127.0.0.1:8765` and opens the address in the default browser. Pass a port as the first argument when needed:

```sh
./run_gallery.sh 9000
```

To start the server without opening a browser, run it directly:

```sh
uv run --no-project python server.py --host 127.0.0.1 --port 8765
```

Stop the server with `Ctrl+C` in the terminal where it is running.

## Folder registration

The home page has two folder-management actions:

- **Choose folders to browse** opens the operating system folder picker. The selected folder is registered for viewing and remains registered after restarting CanvasShelf.
- **Refresh folders** scans the direct child folders of `../Arts/` and appends folders that contain supported image files. This scan is optional; it does not require a server restart.

Registering or removing a folder changes only CanvasShelf's collection list. It never moves, edits, or deletes the local folder or its images. A folder removed from the filesystem is automatically omitted from the site while its configuration entry is retained; restoring the same path makes it available again.

Collection definitions are stored in `gallery_collections.json`. Paths are resolved relative to the CanvasShelf directory, and folders outside the project are stored as relative paths as well. The folder picker accepts an absolute path when necessary and converts it when saving.

The command-line equivalent of **Refresh folders** is:

```sh
./sync_gallery_collections.sh
```

Useful options:

```sh
./sync_gallery_collections.sh --arts-dir /path/to/Arts
./sync_gallery_collections.sh --config /path/to/gallery_collections.json --dry-run
```

Relative arguments are resolved from the CanvasShelf directory. `--dry-run` reports additions without changing the configuration. Only newly discovered direct child folders containing supported images are appended; existing entries keep their order.

## Home page

The **Collection order** selector supports:

- **Manual** — drag cards to reorder them. The order is written to `gallery_collections.json`.
- **Newest** — collections whose images were modified most recently first.
- **Oldest** — collections whose oldest image is earliest first.
- **Name** — collection label in name order.

The selected home-page mode is saved and restored on the next visit. Dragging is available only in Manual mode. A folder added by the refresh action or folder picker is appended after existing entries.

## Collection pages

Each collection page provides:

- A responsive masonry grid for local images.
- Support for AVIF, BMP, GIF, HEIC, JPEG, JPG, PNG, TIF, TIFF, and WebP files.
- Filename search.
- Per-collection image sorting by **Newest**, **Oldest**, or **Name**. The choice is saved in both the browser and the local server, so it is restored after navigation and restart. Name order places images from left to right in each row.
- A memo area above the grid for the folder's root-level `memo.md`.
- An **Edit memo** button that opens the editor only when clicked. Saving creates `memo.md` when it is missing, updates the file in place, and immediately refreshes the displayed memo. Markdown headings (levels 1–3) and bullet lists are rendered. `Cmd/Ctrl+Enter` also saves; memo input is limited to 512 KiB.
- Click-to-enlarge lightbox viewing, arrow-key navigation, and `Esc` to close.
- A delete action with confirmation. Images are moved to the executing user's `.Trash` directory instead of being permanently deleted; an available numbered name is chosen if the Trash already contains the same filename.

## Files and privacy

`gallery_collections.json` contains collection metadata and paths. `.gallery_preferences.json` contains runtime sort preferences and is ignored by Git; the browser also keeps a copy for resilient restoration. Image files and generated local data are excluded from the repository by `.gitignore`.

The server binds to loopback (`127.0.0.1`) by default. Change the bind address explicitly only when you understand the implications of exposing the gallery to another network.

## Development checks

From the directory that contains the `CanvasShelf/` checkout:

```sh
PYTHONPATH=. uv run --no-project python -m unittest discover -s CanvasShelf/tests -v
node --check CanvasShelf/gallery/app.js
uv run --no-project python -m py_compile CanvasShelf/server.py
```

`README_ja.md` is a local Japanese manual and is intentionally excluded from commits.
