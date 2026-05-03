#!/usr/bin/env bash
set -euo pipefail

# Always run from the keyboard-trip root
cd "$(dirname "$0")/.."

OUT_DIR="footage/91_Visual_Contact_Sheets"
INTERVAL_SECONDS="${1:-2}"

export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/private/tmp}"
mkdir -p "$XDG_CACHE_HOME/fontconfig"
mkdir -p "$OUT_DIR"

find \
  footage/01_Trip_Setup \
  footage/02_Drive_To_Titusville \
  footage/03_David_Factory_Visit \
  footage/05_Post_Pickup_Main_Argument \
  footage/06_Car_Trouble_Return \
  footage/07_Home_Demo_Payoff \
  footage/08_Pickups_To_Record \
  -name '*.MOV' -print | sort | while IFS= read -r video; do
    base="$(basename "$video" .MOV)"
    clip_dir="$OUT_DIR/$base"
    mkdir -p "$clip_dir"

    rm -f "$clip_dir"/*.jpg

    echo "Building contact sheets for $video"
    ffmpeg -nostdin -hide_banner -loglevel error -i "$video" \
      -vf "fps=1/${INTERVAL_SECONDS},scale=320:-1,drawtext=fontcolor=white:fontsize=18:box=1:boxcolor=black@0.65:text='%{pts\\:hms}':x=8:y=8,tile=5x6:padding=8:margin=8" \
      "$clip_dir/${base}_sheet_%03d.jpg"
  done

echo "Done. Contact sheets are in $OUT_DIR."
