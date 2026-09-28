#!/usr/bin/env bash
# The 20-s Civ1 game film 'Koloss von Rhodos' (wunderfilm_03_colossus):
#   Cycles render (5 shots, bright look) -> painterly stylize (the film's grade) ->
#   temporal stabilisation (optical flow) -> soundtrack -> MP4 + OGV
# Usage: PYTHON=/path/to/venv/bin/python ./make_colossus20.sh [extra render.py args, e.g. --skip-existing]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python}"
BUILD="${BUILD:-$HERE/build/c20}"
NAME="${NAME:-wunderfilm_03_colossus}"
OUTDIR="${OUTDIR:-$HERE/game_films}"
mkdir -p "$BUILD/png" "$BUILD/png_stab" "$OUTDIR"

# the photographed day sky (CC0, ~20 MB, not in git); the statue is sculpted and cached on first use
ls "$HERE"/assets/hdri/*_nosun.hdr > /dev/null 2>&1 || "$PY" "$HERE/fetch_hdri.py"
"$PY" "$HERE/helios.py" > /dev/null

# render: two processes with two threads each (even / odd frames)
"$PY" "$HERE/render.py" --film colossus20 --out "$BUILD" --no-lines --threads 2 \
  --frames "$(seq -s, 0 2 479)" "$@" &
"$PY" "$HERE/render.py" --film colossus20 --out "$BUILD" --no-lines --threads 2 \
  --frames "$(seq -s, 1 2 479)" "$@" &
wait

# stylize: exposure keys once, then four workers
"$PY" "$HERE/stylize.py" --inp "$BUILD" --out "$BUILD/png" --look paint --frames none --film colossus20
for k in 0 1 2 3; do
  "$PY" "$HERE/stylize.py" --inp "$BUILD" --out "$BUILD/png" --look paint --no-titles --fade-in 0.35 \
    --film colossus20 --frames "$(seq -s, $k 4 479)" > "$BUILD/stylize_$k.log" &
done
wait

# temporal stabilisation, shot by shot (optical flow; real motion passes through);
# the time-lapse shots get the brightness deflicker as well
"$PY" "$HERE/stabilize.py" --inp "$BUILD/png" --meta "$BUILD" --out "$BUILD/png_stab" --deflicker S2,S4 --deflicker-frames 5

"$PY" "$HERE/audio_colossus20.py" --out "$BUILD/soundtrack.wav"

# MP4 for upscaling / preview, OGV (Theora + Vorbis) for Godot
ffmpeg -y -loglevel error -framerate 24 -i "$BUILD/png_stab/frame_%04d.png" -i "$BUILD/soundtrack.wav" \
  -c:v libx264 -preset slow -crf 16 -tune film -pix_fmt yuv420p -profile:v high \
  -c:a aac -b:a 192k -movflags +faststart -shortest "$OUTDIR/$NAME.mp4"
ffmpeg -y -loglevel error -framerate 24 -i "$BUILD/png_stab/frame_%04d.png" -i "$BUILD/soundtrack.wav" \
  -c:v libtheora -q:v 9 -pix_fmt yuv420p -c:a libvorbis -q:a 6 -ar 48000 -shortest "$OUTDIR/$NAME.ogv"
echo "wrote $OUTDIR/$NAME.mp4 and $OUTDIR/$NAME.ogv"
