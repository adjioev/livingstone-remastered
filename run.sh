#!/usr/bin/env bash
# Build (if needed) and start the Livingstone remaster prototype.
#   ./run.sh            build + play
#   ./run.sh --rebuild  wipe the build dir first
set -euo pipefail
cd "$(dirname "$0")/remaster"

if ! command -v cmake >/dev/null || ! pkg-config --exists raylib unicorn 2>/dev/null; then
    echo "Installing dependencies (cmake, raylib, unicorn) via Homebrew..."
    brew install cmake pkgconf raylib unicorn
fi

if [[ "${1:-}" == "--rebuild" ]]; then
    rm -rf build
    shift
fi

[[ -f build/CMakeCache.txt ]] || cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
exec ./build/livingstone "$@"
