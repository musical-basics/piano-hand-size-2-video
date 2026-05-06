#!/usr/bin/env bash
set -euo pipefail

# Fine contact sheet for a specific source range.
# Implements Plan Step 22 / Checklist item 21.
#
# Usage:
#   ./scripts/make_fine_contact_sheet.sh <video> <start_s> <end_s> [interval_s]
#
# Default interval is 0.5s. Output goes to
# footage/92_Fine_Contact_Sheets/<basename>__<start>-<end>__<interval>s/
# so it doesn't pollute the global 2s sheets in 91_Visual_Contact_Sheets/.

cd "$(dirname "$0")/.."

if [ $# -lt 3 ]; then
  echo "usage: $0 <video> <start_s> <end_s> [interval_s]" >&2
  exit 2
fi

VIDEO="$1"
START="$2"
END="$3"
INTERVAL="${4:-0.5}"

if [ ! -f "$VIDEO" ]; then
  echo "error: video not found: $VIDEO" >&2
  exit 1
fi

DURATION=$(python3 -c "print(${END} - ${START})")
BASENAME=$(basename "$VIDEO" .MOV)
BASENAME=$(basename "$BASENAME" .mov)
BASENAME=$(basename "$BASENAME" .MP4)
BASENAME=$(basename "$BASENAME" .mp4)

OUT_DIR="footage/92_Fine_Contact_Sheets/${BASENAME}__${START}-${END}__${INTERVAL}s"
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/*.jpg

export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/private/tmp}"
mkdir -p "$XDG_CACHE_HOME/fontconfig"

echo "Building fine contact sheet:"
echo "  source:    $VIDEO"
echo "  range:     ${START}s → ${END}s  (${DURATION}s)"
echo "  interval:  ${INTERVAL}s"
echo "  output:    $OUT_DIR"

ffmpeg -nostdin -hide_banner -loglevel error \
  -ss "$START" -i "$VIDEO" -t "$DURATION" \
  -vf "fps=1/${INTERVAL},scale=320:-1,drawtext=fontcolor=white:fontsize=18:box=1:boxcolor=black@0.65:text='%{pts\:hms}':x=8:y=8,tile=5x6:padding=8:margin=8" \
  "$OUT_DIR/${BASENAME}_fine_sheet_%03d.jpg"

echo "Done."
ls "$OUT_DIR"
