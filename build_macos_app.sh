#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="API ID Status Checker"
PYTHON_313="${PYTHON_313:-/opt/homebrew/bin/python3.13}"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/api-id-checker-build.XXXXXX")"

cleanup() {
  rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

if [ ! -x "$PYTHON_313" ]; then
  echo "Python 3.13 was not found at $PYTHON_313"
  exit 1
fi

"$PYTHON_313" -m venv "$BUILD_ROOT/venv"
"$BUILD_ROOT/venv/bin/python" -m pip install --upgrade pip
"$BUILD_ROOT/venv/bin/python" -m pip install \
  -r "$PROJECT_DIR/requirements-build.txt"

"$BUILD_ROOT/venv/bin/python" \
  "$PROJECT_DIR/packaging/make_icon.py" \
  "$BUILD_ROOT/AppIcon.icns"

"$BUILD_ROOT/venv/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "com.local.api-id-status-checker" \
  --icon "$BUILD_ROOT/AppIcon.icns" \
  --add-data "$PROJECT_DIR/templates:templates" \
  --add-data "$PROJECT_DIR/static:static" \
  --collect-submodules uvicorn \
  --distpath "$BUILD_ROOT/dist" \
  --workpath "$BUILD_ROOT/work" \
  --specpath "$BUILD_ROOT/spec" \
  "$PROJECT_DIR/mac_app_launcher.py"

rm -rf "$PROJECT_DIR/$APP_NAME.app"
/usr/bin/ditto \
  "$BUILD_ROOT/dist/$APP_NAME.app" \
  "$PROJECT_DIR/$APP_NAME.app"

/usr/bin/plutil \
  -replace CFBundleShortVersionString \
  -string "1.3.0" \
  "$PROJECT_DIR/$APP_NAME.app/Contents/Info.plist"
/usr/bin/plutil \
  -insert CFBundleVersion \
  -string "4" \
  "$PROJECT_DIR/$APP_NAME.app/Contents/Info.plist"
/usr/bin/plutil \
  -insert LSMinimumSystemVersion \
  -string "11.0" \
  "$PROJECT_DIR/$APP_NAME.app/Contents/Info.plist"

/usr/bin/codesign \
  --force \
  --deep \
  --sign - \
  "$PROJECT_DIR/$APP_NAME.app"

echo "Built: $PROJECT_DIR/$APP_NAME.app"
