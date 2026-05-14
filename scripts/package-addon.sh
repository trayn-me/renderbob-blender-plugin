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

# Ship source .py only. Do NOT compile with system `python3` and strip sources:
# Blender bundles its own Python (e.g. 3.11 in 4.2.x); .pyc from another minor
# version causes "bad magic number" on import (e.g. b'\\xcb\\r\\r\\n').
cp "$ROOT_DIR/__init__.py" "$BUILD_DIR/__init__.py"
cp "$ROOT_DIR/blender_manifest.toml" "$BUILD_DIR/blender_manifest.toml"
cp -R "$ROOT_DIR/renderbob_plugin/." "$BUILD_DIR/renderbob_plugin/"

# Never bundle stray bytecode from a dev machine.
find "$BUILD_DIR" -type d -name '__pycache__' 2>/dev/null | while read -r d; do
  rm -rf "$d"
done
find "$BUILD_DIR" -name '*.pyc' -delete 2>/dev/null || true
find "$BUILD_DIR" -name '*.pyo' -delete 2>/dev/null || true

(
  cd "$BUILD_DIR"
  zip -r "$ZIP_PATH" \
    "__init__.py" \
    "blender_manifest.toml" \
    "renderbob_plugin" \
    -x "*/__pycache__/*" \
    -x "*.pyc" \
    -x "*.pyo"
)

echo "Packaged addon at: $ZIP_PATH"
