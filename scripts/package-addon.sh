#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
ZIP_PATH="$DIST_DIR/renderbob-addon.zip"
BUILD_DIR="$DIST_DIR/build"

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/renderbob_plugin"

# Keep only the root __init__.py in source form (for Blender metadata), and
# package the internal plugin package as bytecode-only to make casual reading harder.
cp "$ROOT_DIR/__init__.py" "$BUILD_DIR/__init__.py"
cp "$ROOT_DIR/blender_manifest.toml" "$BUILD_DIR/blender_manifest.toml"
cp -R "$ROOT_DIR/renderbob_plugin/." "$BUILD_DIR/renderbob_plugin/"

PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m compileall -q -b "$BUILD_DIR/renderbob_plugin"
BUILD_DIR="$BUILD_DIR" "$PYTHON_BIN" - <<'PY'
import os
import pathlib
import shutil

build_dir = pathlib.Path(os.environ["BUILD_DIR"])
plugin_dir = build_dir / "renderbob_plugin"

for source_file in plugin_dir.rglob("*.py"):
    source_file.unlink()

for pycache_dir in build_dir.rglob("__pycache__"):
    shutil.rmtree(pycache_dir, ignore_errors=True)
PY

(
  cd "$BUILD_DIR"
  zip -r "$ZIP_PATH" \
    "__init__.py" \
    "blender_manifest.toml" \
    "renderbob_plugin" \
    -x "*/__pycache__/*"
)

echo "Packaged addon at: $ZIP_PATH"
