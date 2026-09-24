#!/usr/bin/env bash
# Full pipeline for the Great Lighthouse time-lapse:
#   Cycles render (beauty + ink passes) -> comic stylization + titles -> soundtrack -> MP4
# Usage: PYTHON=/path/to/venv/bin/python ./make_film.sh [extra render.py args, e.g. --skip-existing]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python}"
BUILD="${BUILD:-$HERE/build}"
OUT="${OUT:-$HERE/great_lighthouse_timelapse.mp4}"

"$PY" "$HERE/render.py" --out "$BUILD/render" "$@"
"$PY" "$HERE/stylize.py" --inp "$BUILD/render" --out "$BUILD/frames"
"$PY" "$HERE/audio.py" --out "$BUILD/soundtrack.wav"
ffmpeg -y -loglevel error -framerate 24 -i "$BUILD/frames/frame_%04d.png" -i "$BUILD/soundtrack.wav" \
  -c:v libx264 -preset slow -crf 17 -tune film -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart -shortest "$OUT"
echo "wrote $OUT"
