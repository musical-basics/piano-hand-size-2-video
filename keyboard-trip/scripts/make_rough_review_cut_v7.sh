#!/usr/bin/env bash
set -euo pipefail

# Always run from the keyboard-trip root
cd "$(dirname "$0")/.."

OUT_DIR="renders/review_cuts"
OUT_FILE="$OUT_DIR/piano_hand_size_part2_rough_cut_v7.mp4"
WORK_DIR="$(mktemp -d /private/tmp/piano-hand-size-rough-cut-v7.XXXXXX)"
SEG_DIR="$WORK_DIR/segments"
CONCAT_FILE="$WORK_DIR/concat.txt"
# Section-specific music beds, all generated via Replicate Stable Audio 2.5
# (see scripts/generate_music_bed.py). The procedural drone pass8_travel_bed
# is gone. MUSIC_BED is reassigned before each section call so the existing
# helpers pick up the right file.
MUSIC_LATE_NIGHT="audio/music/ai_v1_late_night_drive_60s.mp3"
MUSIC_MORNING="audio/music/ai_morning_road_60s.mp3"
MUSIC_LAKE="audio/music/ai_lake_pause_60s.mp3"
MUSIC_BREAKDOWN="audio/music/ai_breakdown_return_60s.mp3"
MUSIC_BED="$MUSIC_LATE_NIGHT"
MUSIC_CARD_VOLUME="0.18"
MUSIC_UNDER_VO_VOLUME="0.16"
MUSIC_ONLY_VOLUME="0.22"

W=1280
H=720
FPS=30
SR=48000

FONT="/System/Library/Fonts/Supplemental/Arial.ttf"
if [ ! -f "$FONT" ]; then
  FONT="/System/Library/Fonts/Supplemental/Helvetica.ttf"
fi

mkdir -p "$OUT_DIR" "$SEG_DIR"
: > "$CONCAT_FILE"

segment_index=0
montage_index=0

set_next_out() {
  segment_index=$((segment_index + 1))
  NEXT_OUT="$(printf "%s/seg_%03d.mp4" "$SEG_DIR" "$segment_index")"
}

append_concat() {
  local file="$1"
  printf "file '%s'\n" "$file" >> "$CONCAT_FILE"
}

ensure_music_beds() {
  for bed in "$MUSIC_LATE_NIGHT" "$MUSIC_MORNING" "$MUSIC_LAKE" "$MUSIC_BREAKDOWN"; do
    if [ ! -f "$bed" ]; then
      echo "Missing music bed: $bed" >&2
      echo "Generate via: python3 scripts/generate_music_bed.py \"<prompt>\" 60 <basename>" >&2
      exit 1
    fi
  done
}

rotation_filter() {
  local rotate="${1:-none}"
  case "$rotate" in
    cw) printf "transpose=1," ;;
    ccw) printf "transpose=2," ;;
    180) printf "transpose=2,transpose=2," ;;
    none|"") printf "" ;;
    *) echo "Unknown rotation: $rotate" >&2; exit 1 ;;
  esac
}

video_filter() {
  local rotate="${1:-none}"
  printf "%sscale=%s:%s:force_original_aspect_ratio=decrease,pad=%s:%s:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=%s,format=yuv420p" \
    "$(rotation_filter "$rotate")" "$W" "$H" "$W" "$H" "$FPS"
}

encode_file() {
  local out="$1"
  shift
  ffmpeg -y -hide_banner -loglevel error "$@" \
    -c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p \
    -c:a aac -b:a 128k -ar "$SR" -ac 2 \
    -movflags +faststart \
    "$out"
}

encode_segment() {
  local out="$1"
  shift
  encode_file "$out" "$@"
  append_concat "$out"
}

add_video() {
  local src="$1"
  local start="$2"
  local duration="$3"
  local rotate="${4:-none}"
  local out
  set_next_out
  out="$NEXT_OUT"

  echo "Adding video: $src @ $start for ${duration}s rotation=${rotate}"
  encode_segment "$out" \
    -ss "$start" -t "$duration" -i "$src" \
    -vf "$(video_filter "$rotate")" \
    -map 0:v:0 -map 0:a:0? \
    -shortest
}

add_still() {
  local src="$1"
  local duration="$2"
  local rotate="${3:-none}"
  local out
  set_next_out
  out="$NEXT_OUT"

  echo "Adding still: $src for ${duration}s rotation=${rotate}"
  encode_segment "$out" \
    -loop 1 -framerate "$FPS" -t "$duration" -i "$src" \
    -f lavfi -t "$duration" -i "anullsrc=channel_layout=stereo:sample_rate=$SR" \
    -vf "$(video_filter "$rotate")" \
    -map 0:v:0 -map 1:a:0 \
    -shortest
}

add_card() {
  local duration="$1"
  local text="$2"
  local out text_file vf
  set_next_out
  out="$NEXT_OUT"
  text_file="$WORK_DIR/card_${segment_index}.txt"
  printf "%s\n" "$text" > "$text_file"

  vf="drawtext=fontfile=${FONT}:textfile=${text_file}:fontcolor=white:fontsize=40:line_spacing=14:x=(w-text_w)/2:y=(h-text_h)/2"

  echo "Adding card for ${duration}s: $text"
  encode_segment "$out" \
    -f lavfi -t "$duration" -i "color=c=0x111111:s=${W}x${H}:r=$FPS" \
    -f lavfi -t "$duration" -i "anullsrc=channel_layout=stereo:sample_rate=$SR" \
    -vf "$vf" \
    -map 0:v:0 -map 1:a:0 \
    -shortest
}

add_card_with_music() {
  local duration="$1"
  local text="$2"
  local out text_file vf fade_out_start
  set_next_out
  out="$NEXT_OUT"
  text_file="$WORK_DIR/card_${segment_index}.txt"
  printf "%s\n" "$text" > "$text_file"
  fade_out_start="$(awk -v d="$duration" 'BEGIN { v=d-0.7; if (v<0) v=0; printf "%.3f", v }')"

  vf="drawtext=fontfile=${FONT}:textfile=${text_file}:fontcolor=white:fontsize=40:line_spacing=14:x=(w-text_w)/2:y=(h-text_h)/2"

  echo "Adding music card for ${duration}s: $text"
  encode_segment "$out" \
    -f lavfi -t "$duration" -i "color=c=0x111111:s=${W}x${H}:r=$FPS" \
    -stream_loop -1 -i "$MUSIC_BED" \
    -vf "$vf" \
    -filter:a "aresample=${SR},volume=${MUSIC_CARD_VOLUME},atrim=0:${duration},afade=t=in:st=0:d=0.5,afade=t=out:st=${fade_out_start}:d=0.7" \
    -map 0:v:0 -map 1:a:0 \
    -t "$duration"
}

start_montage() {
  montage_index=$((montage_index + 1))
  MONTAGE_DIR="$WORK_DIR/montage_${montage_index}"
  MONTAGE_CONCAT="$MONTAGE_DIR/concat.txt"
  MONTAGE_PIECE_INDEX=0
  mkdir -p "$MONTAGE_DIR"
  : > "$MONTAGE_CONCAT"
}

append_montage() {
  local file="$1"
  printf "file '%s'\n" "$file" >> "$MONTAGE_CONCAT"
}

montage_piece_video() {
  local src="$1"
  local start="$2"
  local duration="$3"
  local rotate="${4:-none}"
  local out
  MONTAGE_PIECE_INDEX=$((MONTAGE_PIECE_INDEX + 1))
  out="$(printf "%s/piece_%03d.mp4" "$MONTAGE_DIR" "$MONTAGE_PIECE_INDEX")"

  echo "  montage video: $src @ $start for ${duration}s rotation=${rotate}"
  encode_file "$out" \
    -ss "$start" -t "$duration" -i "$src" \
    -f lavfi -t "$duration" -i "anullsrc=channel_layout=stereo:sample_rate=$SR" \
    -vf "$(video_filter "$rotate")" \
    -map 0:v:0 -map 1:a:0 \
    -shortest
  append_montage "$out"
}

montage_piece_still() {
  local src="$1"
  local duration="$2"
  local rotate="${3:-none}"
  local out
  MONTAGE_PIECE_INDEX=$((MONTAGE_PIECE_INDEX + 1))
  out="$(printf "%s/piece_%03d.mp4" "$MONTAGE_DIR" "$MONTAGE_PIECE_INDEX")"

  echo "  montage still: $src for ${duration}s rotation=${rotate}"
  encode_file "$out" \
    -loop 1 -framerate "$FPS" -t "$duration" -i "$src" \
    -f lavfi -t "$duration" -i "anullsrc=channel_layout=stereo:sample_rate=$SR" \
    -vf "$(video_filter "$rotate")" \
    -map 0:v:0 -map 1:a:0 \
    -shortest
  append_montage "$out"
}

finish_montage_with_vo() {
  local vo="$1"
  local label="$2"
  local silent_video="$MONTAGE_DIR/silent_video.mp4"
  local out
  set_next_out
  out="$NEXT_OUT"

  echo "Finishing VO montage: $label with $vo"
  ffmpeg -y -hide_banner -loglevel error \
    -f concat -safe 0 -i "$MONTAGE_CONCAT" \
    -c copy \
    "$silent_video"

  ffmpeg -y -hide_banner -loglevel error \
    -i "$silent_video" -i "$vo" \
    -map 0:v:0 -map 1:a:0 \
    -c:v copy \
    -c:a aac -b:a 160k -ar "$SR" -ac 2 \
    -shortest \
    -movflags +faststart \
    "$out"
  append_concat "$out"
}

finish_montage_with_vo_and_music() {
  local vo="$1"
  local label="$2"
  local silent_video="$MONTAGE_DIR/silent_video.mp4"
  local out montage_duration fade_out_start
  set_next_out
  out="$NEXT_OUT"

  echo "Finishing VO+music montage: $label with $vo"
  ffmpeg -y -hide_banner -loglevel error \
    -f concat -safe 0 -i "$MONTAGE_CONCAT" \
    -c copy \
    "$silent_video"

  montage_duration="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$silent_video")"
  fade_out_start="$(awk -v d="$montage_duration" 'BEGIN { v=d-1.2; if (v<0) v=0; printf "%.3f", v }')"

  ffmpeg -y -hide_banner -loglevel error \
    -i "$silent_video" -i "$vo" -stream_loop -1 -i "$MUSIC_BED" \
    -filter_complex "[1:a]aresample=${SR},volume=1.0,apad=whole_dur=${montage_duration}[vo];[2:a]aresample=${SR},volume=${MUSIC_UNDER_VO_VOLUME},atrim=0:${montage_duration},afade=t=in:st=0:d=0.8,afade=t=out:st=${fade_out_start}:d=1.2[music];[vo][music]amix=inputs=2:duration=first:dropout_transition=0[a]" \
    -map 0:v:0 -map "[a]" \
    -c:v copy \
    -c:a aac -b:a 160k -ar "$SR" -ac 2 \
    -t "$montage_duration" \
    -movflags +faststart \
    "$out"
  append_concat "$out"
}

finish_montage_with_music() {
  local label="$1"
  local silent_video="$MONTAGE_DIR/silent_video.mp4"
  local out montage_duration fade_out_start
  set_next_out
  out="$NEXT_OUT"

  echo "Finishing music montage: $label"
  ffmpeg -y -hide_banner -loglevel error \
    -f concat -safe 0 -i "$MONTAGE_CONCAT" \
    -c copy \
    "$silent_video"
  montage_duration="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$silent_video")"
  fade_out_start="$(awk -v d="$montage_duration" 'BEGIN { v=d-1.2; if (v<0) v=0; printf "%.3f", v }')"

  ffmpeg -y -hide_banner -loglevel error \
    -i "$silent_video" -stream_loop -1 -i "$MUSIC_BED" \
    -filter_complex "[1:a]aresample=${SR},volume=${MUSIC_ONLY_VOLUME},atrim=0:${montage_duration},afade=t=in:st=0:d=0.8,afade=t=out:st=${fade_out_start}:d=1.2[music]" \
    -map 0:v:0 -map "[music]" \
    -c:v copy \
    -c:a aac -b:a 128k -ar "$SR" -ac 2 \
    -shortest \
    -movflags +faststart \
    "$out"
  append_concat "$out"
}

ensure_music_beds

# Cold open. Pass 10 cuts the home-payoff flash entirely (was 8s) — strict
# chronology: don't show the destination before we've left.
MUSIC_BED="$MUSIC_LATE_NIGHT"
add_video "footage/01_Trip_Setup/001_IMG_0256_0142am_trip_setup.MOV" 0 16
add_card_with_music 3 $'P056 PLACEHOLDER\nHand/key comparison flash'
add_card_with_music 5 $'I drove overnight for a keyboard\nmost pianists have never tried.'

# Setup: fine edit removes the false start and repeated ending line.
add_video "footage/08_Pickups_To_Record/055_PICKUP_front_facing_intro.MOV" 0 6
add_video "footage/08_Pickups_To_Record/055_PICKUP_front_facing_intro.MOV" 13.5 17

# VO_01 montage (40s) — Pass 10 chronology fix: only night/early-trip
# imagery, no factory keyboard close-ups (those moved to the factory
# section where they belong). Order tracks the trip's actual timeline.
MUSIC_BED="$MUSIC_LATE_NIGHT"
start_montage
montage_piece_still "footage/90_Reference_Frames/IMG_0256.jpg" 8
montage_piece_still "footage/90_Reference_Frames/IMG_0257.jpg" 6
montage_piece_video "footage/01_Trip_Setup/004_IMG_0259_sheets_stop_middle_of_nowhere.MOV" 0 7
montage_piece_still "footage/90_Reference_Frames/IMG_0260.jpg" 5
montage_piece_video "footage/02_Drive_To_Titusville/010_IMG_0266_drive_broll_2.MOV" 0 8
montage_piece_still "footage/90_Reference_Frames/IMG_0265.jpg" 6
finish_montage_with_vo_and_music "audio/voiceovers/VO_01_late_night_drive.wav" "VO 01 late-night drive"

# Clear size setup, rotated per review notes. (Stays as the visual answer
# to VO_01's "what I drove for" — first time we actually see the keyboards.)
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 49 16 ccw

# VO 02 Gas Station And Snacks — uses morning_road music for the warmer,
# brighter daytime travel feel.
MUSIC_BED="$MUSIC_MORNING"
start_montage
montage_piece_video "footage/01_Trip_Setup/002_IMG_0257_hagerstown_gas_station.MOV" 0 6 cw
montage_piece_still "footage/90_Reference_Frames/IMG_0258.jpg" 3
montage_piece_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 103 5
montage_piece_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 19 3
finish_montage_with_vo_and_music "audio/voiceovers/VO_02_gas_station_and_snacks.wav" "VO 02 gas station and snacks"

# Preserve the snack/car-nap vlog beats with original audio after VO.
add_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 0 6
add_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 19 5

# Nap section a-roll.
add_video "footage/01_Trip_Setup/005_IMG_0260_waking_up_after_car_nap.MOV" 0 6
add_video "footage/01_Trip_Setup/006_IMG_0261_car_nap_recovery_drive_resumes.MOV" 0 5
add_video "footage/01_Trip_Setup/006_IMG_0261_car_nap_recovery_drive_resumes.MOV" 29 4

# VO 03 Car Nap — Pass 10 dedupe: removed second IMG_0260 still (was
# a repeat of the one used in VO_01), removed 010_IMG_0266 (now in VO_01).
MUSIC_BED="$MUSIC_MORNING"
start_montage
montage_piece_still "footage/90_Reference_Frames/IMG_0261.jpg" 4
montage_piece_video "footage/01_Trip_Setup/005_IMG_0260_waking_up_after_car_nap.MOV" 6 6
montage_piece_still "footage/90_Reference_Frames/IMG_0263.jpg" 4
finish_montage_with_vo_and_music "audio/voiceovers/VO_03_car_nap.wav" "VO 03 car nap"

# Pennsylvania road texture — VO 04 keeps its current visuals.
add_video "footage/02_Drive_To_Titusville/007_IMG_0263_morning_highway_update.MOV" 21 10
MUSIC_BED="$MUSIC_MORNING"
start_montage
montage_piece_video "footage/02_Drive_To_Titusville/008_IMG_0264_pennsylvania_scenery.MOV" 0 8
montage_piece_video "footage/02_Drive_To_Titusville/009_IMG_0265_drive_broll_1.MOV" 0 7
montage_piece_still "footage/90_Reference_Frames/IMG_0267.jpg" 5
finish_montage_with_vo_and_music "audio/voiceovers/VO_04_pennsylvania_road.wav" "VO 04 Pennsylvania road"
add_video "footage/02_Drive_To_Titusville/011_IMG_0267_in_the_woods_almost_there.MOV" 0 12
add_video "footage/02_Drive_To_Titusville/012_IMG_0268_double_big_mac_lunch.MOV" 0 4

# David's keyboard world. Rotations applied from review notes.
# Pass 10 removes the trailing 9-second slideshow of three back-to-back
# keyboard close-up stills (030/031/032) — the lineup b-roll above already
# covers the visual case for the title card that follows.
add_video "footage/03_David_Factory_Visit/013_IMG_0269_keyboard_21_intro.MOV" 0 7
add_video "footage/03_David_Factory_Visit/013_IMG_0269_keyboard_21_intro.MOV" 7 10
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 0 12 ccw
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 25 10 ccw
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 49 15 ccw
add_video "footage/03_David_Factory_Visit/019_IMG_0275_ds55_pickup_and_wrap.MOV" 0 10
add_video "footage/03_David_Factory_Visit/019_IMG_0275_ds55_pickup_and_wrap.MOV" 60 25
add_video "footage/03_David_Factory_Visit/027_IMG_0283_athena_internals_reconnaissance.MOV" 0 12 ccw
add_video "footage/03_David_Factory_Visit/027_IMG_0283_athena_internals_reconnaissance.MOV" 29 15 ccw

# Main argument
add_card 3 "The real reason key size matters"
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 0 24
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 36 25
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 94 24
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 125 22
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 192 30

# The trip fights back. Lake gets VO 05 with the contemplative lake_pause
# bed; mileage extended from 4s to 6s.
MUSIC_BED="$MUSIC_LAKE"
start_montage
montage_piece_video "footage/05_Post_Pickup_Main_Argument/042_IMG_0298_tionesta_lake_cutaway.MOV" 0 7
montage_piece_video "footage/05_Post_Pickup_Main_Argument/043_IMG_0299_lake_overlook_broll.MOV" 0 7
montage_piece_video "footage/05_Post_Pickup_Main_Argument/044_IMG_0300_177777_mileage.MOV" 0 6
montage_piece_still "footage/90_Reference_Frames/IMG_0300.jpg" 2
finish_montage_with_vo_and_music "audio/voiceovers/VO_05_lake_pause.wav" "VO 05 lake pause"

# Breakdown + return — unresolved-tension music for the saga arc.
add_video "footage/06_Car_Trouble_Return/048_IMG_0304_hotel_car_broke_down.MOV" 0 8
MUSIC_BED="$MUSIC_BREAKDOWN"
start_montage
montage_piece_still "footage/90_Reference_Frames/IMG_0304.jpg" 4
montage_piece_video "footage/06_Car_Trouble_Return/049_IMG_0305_car_fixed_heading_home.MOV" 0 8
montage_piece_video "footage/06_Car_Trouble_Return/050_IMG_0306_beautiful_return_drive.MOV" 0 6
montage_piece_video "footage/06_Car_Trouble_Return/053_IMG_0309_highway_home_broll.MOV" 0 8
finish_montage_with_vo_and_music "audio/voiceovers/VO_06_breakdown_and_return.wav" "VO 06 breakdown and return"

# Home payoff
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 0 20
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 43 18
add_card 5 $'P056 PLACEHOLDER\nStandard vs DS 6.0 vs DS 5.5'
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 71 24
add_card 5 $'My current take\nTry DS 6.0 and DS 5.5 if possible.\nUnder ~8.2 inches: consider DS 5.5 too.'
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 126 12
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 154 18
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 178 18
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 221 35
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 296 13
add_card 7 $'Part 3:\nDS 6.0 vs DS 5.5 comparison?'

echo "Concatenating segments..."
ffmpeg -y -hide_banner -loglevel error \
  -f concat -safe 0 -i "$CONCAT_FILE" \
  -c copy \
  "$OUT_FILE"

echo "Wrote $OUT_FILE"
echo "Temporary segment workdir: $WORK_DIR"
