#!/usr/bin/env bash
# The 20-s Civ1 game film 'Der Leuchtturm' (wunderfilm_04_lighthouse):
#   Cycles render (5 shots, bright look) -> painterly stylize -> soundtrack -> MP4 + OGV
# Usage: PYTHON=/path/to/venv/bin/python ./make_lighthouse20.sh [extra render.py args, e.g. --skip-existing]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python}"
BUILD="${BUILD:-$HERE/build/l20}"
NAME="${NAME:-wunderfilm_04_lighthouse}"
OUTDIR="${OUTDIR:-$HERE/game_films}"
mkdir -p "$BUILD/png" "$OUTDIR"

# render: two processes with two threads each (even / odd frames)
"$PY" "$HERE/render.py" --film lighthouse20 --out "$BUILD" --no-lines --threads 2 \
  --frames "$(seq -s, 0 2 479)" "$@" &
"$PY" "$HERE/render.py" --film lighthouse20 --out "$BUILD" --no-lines --threads 2 \
  --frames "$(seq -s, 1 2 479)" "$@" &
wait

# stylize: exposure keys once, then four workers
"$PY" "$HERE/stylize.py" --inp "$BUILD" --out "$BUILD/png" --look paint --frames none
for k in 0 1 2 3; do
  "$PY" "$HERE/stylize.py" --inp "$BUILD" --out "$BUILD/png" --look paint --no-titles --fade-in 0.35 \
    --frames "$(seq -s, $k 4 479)" > "$BUILD/stylize_$k.log" &
done
wait

"$PY" "$HERE/audio_lighthouse20.py" --out "$BUILD/soundtrack.wav"

# MP4 for upscaling / preview, OGV (Theora + Vorbis) for Godot
ffmpeg -y -loglevel error -framerate 24 -i "$BUILD/png/frame_%04d.png" -i "$BUILD/soundtrack.wav" \
  -c:v libx264 -preset slow -crf 16 -tune film -pix_fmt yuv420p -profile:v high \
  -c:a aac -b:a 192k -movflags +faststart -shortest "$OUTDIR/$NAME.mp4"
ffmpeg -y -loglevel error -framerate 24 -i "$BUILD/png/frame_%04d.png" -i "$BUILD/soundtrack.wav" \
  -c:v libtheora -q:v 9 -pix_fmt yuv420p -c:a libvorbis -q:a 6 -ar 48000 -shortest "$OUTDIR/$NAME.ogv"
echo "wrote $OUTDIR/$NAME.mp4 and $OUTDIR/$NAME.ogv"
