#!/usr/bin/env bash
# Build the macOS app: self-contained engine + HD assets, double-click to play.
#   ./make_app.sh                       -> dist/Livingstone Remastered.app (no game file: the
#                                          player drops their own LSTONE.COM on first launch)
#   ./make_app.sh --edition alan        -> dist/Alan Jones.app (family edition title screen)
#   ./make_app.sh --with-game           -> also embed original/LSTONE.COM (private builds only)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# Python with Pillow for the icon and title logo: a project venv, created on first use.
if [[ -n "${PYTHON:-}" ]]; then
    PY="$PYTHON"
else
    PY="$ROOT/.venv/bin/python"
    if ! "$PY" -c "import PIL" 2>/dev/null; then
        echo "Setting up Python tools (.venv with Pillow)..."
        python3 -m venv "$ROOT/.venv"
        "$PY" -m pip install -q -r "$ROOT/tools/requirements.txt"
    fi
fi
EDITION=release
WITH_GAME=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --edition) EDITION="$2"; shift 2 ;;
        --with-game) WITH_GAME=1; shift ;;
        *) echo "unknown option $1" >&2; exit 1 ;;
    esac
done
case "$EDITION" in
    release) NAME="Livingstone Remastered"; EXE=Livingstone; ID=livingstone.remastered; BADGE=HD ;;
    alan)    NAME="Alan Jones";             EXE=AlanJones;   ID=home.dads.alanjones;    BADGE='$60' ;;
    *) echo "unknown edition $EDITION" >&2; exit 1 ;;
esac
APP="$ROOT/dist/$NAME.app"

cmake -S "$ROOT/remaster" -B "$ROOT/remaster/build-app" -DCMAKE_BUILD_TYPE=Release -DAPP_BUNDLE=ON \
    -DWINDOW_TITLE="$NAME" >/dev/null
cmake --build "$ROOT/remaster/build-app" -j

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/assets"
cp "$ROOT/remaster/build-app/livingstone" "$APP/Contents/MacOS/$EXE"
for d in rooms sprites anim props shaders glow; do
    cp -R "$ROOT/remaster/assets/$d" "$APP/Contents/Resources/assets/"
done
# title screen for this edition (the logo is drawn into the title room's background)
"$PY" "$ROOT/tools/gen_rooms.py" --logo --edition "$EDITION" \
    --out "$APP/Contents/Resources/assets/rooms/room_3d.png" >/dev/null
[[ $WITH_GAME == 1 ]] && cp "$ROOT/original/LSTONE.COM" "$APP/Contents/Resources/"

ICONSET="$(mktemp -d)/AppIcon.iconset"
"$PY" "$ROOT/tools/make_icon.py" "$ICONSET" "$BADGE" >/dev/null
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>$NAME</string>
    <key>CFBundleDisplayName</key><string>$NAME</string>
    <key>CFBundleIdentifier</key><string>$ID</string>
    <key>CFBundleExecutable</key><string>$EXE</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true  # ad-hoc: required on Apple silicon
echo "built: $APP ($(du -sh "$APP" | cut -f1))$([[ $WITH_GAME == 1 ]] && echo ', game embedded')"
