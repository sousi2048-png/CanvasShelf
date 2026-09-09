$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

foreach ($GeneratedDir in @("build", "dist", "release")) {
    if (Test-Path $GeneratedDir) {
        Remove-Item -Recurse -Force $GeneratedDir
    }
}

# uvが管理するPython環境でPyInstallerを実行する（venvやpipは使わない）。
uv python install 3.12
uvx --python 3.12 --from "pyinstaller==6.22.2" pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name CanvasShelf `
    --specpath build `
    --paths . `
    --hidden-import sync_gallery_collections `
    --add-data "$ProjectDir/gallery;gallery" `
    server.py

New-Item -ItemType Directory -Force release | Out-Null
Compress-Archive -Path "dist/CanvasShelf.exe" -DestinationPath "release/CanvasShelf-windows-x64.zip" -Force
Write-Host "作成しました: release/CanvasShelf-windows-x64.zip"
