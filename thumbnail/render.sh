#!/usr/bin/env bash
# render.sh <folder-thumbnail>: setiap <section data-name=...> di slides.html -> fastwork-<n>-<nama>.png
# (1280x720, dirender 2x lewat Microsoft Edge headless lalu diperkecil). Windows + Git Bash + Python/Pillow.
set -e
DIR=$(cd "$1" && pwd -W)
EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
n=0
for name in $(grep -o 'data-name="[^"]*"' "$1/slides.html" | cut -d'"' -f2); do
  n=$((n + 1))
  PROFILE=$(mktemp -d)
  "$EDGE" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --window-size=1280,720 \
    --virtual-time-budget=8000 --allow-file-access-from-files --user-data-dir="$(cygpath -w "$PROFILE")" \
    --screenshot="$DIR\\_render.png" "file:///$DIR/slides.html#$n" 2>/dev/null
  rm -rf "$PROFILE"
  python -c "
from PIL import Image; import sys
Image.open(sys.argv[1]).convert('RGB').resize((1280, 720), Image.LANCZOS).save(sys.argv[2])" "$DIR\\_render.png" "$DIR\\fastwork-$n-$name.png"
  echo "fastwork-$n-$name.png"
done
rm -f "$1/_render.png"
