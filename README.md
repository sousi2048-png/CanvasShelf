# CanvasShelf

CanvasShelf is a local Pinterest-style image gallery. It serves the shared image collections under `../Arts/` and keeps the gallery UI separate from the Pinterest downloader extension.

## Run

Install [uv](https://docs.astral.sh/uv/) and run:

```sh
./run_gallery.sh
```

The server opens `http://127.0.0.1:8765/`. The home page lists configured collections from `gallery_collections.json`; each collection has a responsive masonry layout, memo display, search, and lightbox preview.

Use **Refresh folders** on the home page to scan `../Arts/` and register newly added image folders without restarting the server. Use **Choose folders to browse** to register any local folder; registration only changes the gallery configuration and never moves or deletes local files. Each collection remembers its own sort order (newest, oldest, or name) in the browser and local server. Name sorting flows left-to-right in rows.

Hover an image and choose the trash icon to move it to the operating system's Trash. A confirmation is required, and files are never permanently deleted by the gallery.

## Add collections

Add an entry to `gallery_collections.json`, choose a folder from the home page, or place a new image folder under `../Arts/` and run:

```sh
./sync_gallery_collections.sh
```

The synchronizer appends only new image directories and supports `--dry-run` to preview changes. Relative paths in the configuration are resolved from this directory.
