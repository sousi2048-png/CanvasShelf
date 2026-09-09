# CanvasShelf

CanvasShelf is a local image viewer that arranges images in a responsive masonry layout. It can register image folders on the local computer and keeps the viewer configuration separate from the ShortcutSave downloader extension.

No particular folder layout is required. If an `../Arts/` directory exists next to the project, CanvasShelf can scan it as a convenience; otherwise, folders can be registered directly from the home page.

## Run

Install [uv](https://docs.astral.sh/uv/) and run:

```sh
./run_gallery.sh
```

Pass a different port as the first argument when needed:

```sh
./run_gallery.sh 9000
```

The server opens `http://127.0.0.1:8765/` by default. The home page lists the registered collections from `gallery_collections.json`; collections whose local folder no longer exists are omitted automatically.

## Manage folders

The home page provides two folder-management actions:

- **Choose folders to browse** registers any local image folder. Registering or removing a folder only changes the gallery configuration; it never moves, edits, or deletes the local folder or its images. Registered paths are stored in `gallery_collections.json`.
- **Refresh folders** scans `../Arts/` relative to the CanvasShelf directory and appends newly added child folders that contain supported images. This is optional and does not require a server restart.

The refresh action is also available from the command line:

```sh
./sync_gallery_collections.sh
```

Use `--arts-dir /path/to/Arts` to scan another directory or `--dry-run` to preview additions without writing the configuration. Relative paths in the configuration are resolved from the CanvasShelf directory; absolute paths are also accepted for folders outside the project.

The home page can display collections in **manual**, **newest**, **oldest**, or **name** order. Newest and oldest use the modification times of the images in each collection. The selected mode is saved for the next visit. In manual mode, drag a collection card to a new position; the order is saved to `gallery_collections.json`. New folders discovered by a refresh or added from the folder picker are appended after the existing entries.

## Browse collections

Each collection page provides:

- A responsive masonry layout for local images.
- The folder's root-level `memo.md`, when present, above the image grid.
- An editor for the folder's root-level `memo.md`, opened with **Edit memo**; saving creates the file when it does not exist. Markdown headings and lists are rendered above the grid. `Cmd/Ctrl+Enter` also saves the memo.
- Filename search and per-collection sorting by newest, oldest, or name.
- Persistent sort preferences in the browser and local server. Name sorting places images from left to right in each row.
- Click-to-enlarge lightbox preview, with arrow-key navigation and `Esc` to close.
- A trash action with confirmation that moves an image to the operating system's Trash instead of permanently deleting it.

Images and local configuration are intentionally excluded from this repository; each user supplies and registers their own folders.
