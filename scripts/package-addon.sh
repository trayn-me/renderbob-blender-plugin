#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
ZIP_PATH="$DIST_DIR/renderbob-addon.zip"

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"

cd "$ROOT_DIR"
zip -r "$ZIP_PATH" \
  "__init__.py" \
  "blender_manifest.toml" \
  "renderbob_plugin" \
  -x "*/__pycache__/*" "*.pyc"

echo "Packaged addon at: $ZIP_PATH"
