#!/usr/bin/env bash
set -euo pipefail

# Always run from the keyboard-trip root
cd "$(dirname "$0")/.."

OUT_DIR="renders/review_cuts"
OUT_FILE="$OUT_DIR/piano_hand_size_part2_rough_cut_v1.mp4"
WORK_DIR="$(mktemp -d /private/tmp/piano-hand-size-rough-cut.XXXXXX)"
SEG_DIR="$WORK_DIR/segments"
CONCAT_FILE="$WORK_DIR/concat.txt"

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

set_next_out() {
  segment_index=$((segment_index + 1))
  NEXT_OUT="$(printf "%s/seg_%03d.mp4" "$SEG_DIR" "$segment_index")"
}

append_concat() {
  local file="$1"
  printf "file '%s'\n" "$file" >> "$CONCAT_FILE"
}

video_filter() {
  printf "scale=%s:%s:force_original_aspect_ratio=decrease,pad=%s:%s:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=%s,format=yuv420p" "$W" "$H" "$W" "$H" "$FPS"
}

encode_segment() {
  local out="$1"
  shift
  ffmpeg -y -hide_banner -loglevel error "$@" \
    -c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p \
    -c:a aac -b:a 128k -ar "$SR" -ac 2 \
    -movflags +faststart \
    "$out"
  append_concat "$out"
}

add_video() {
  local src="$1"
  local start="$2"
  local duration="$3"
  local out
  set_next_out
  out="$NEXT_OUT"

  echo "Adding video: $src @ $start for ${duration}s"
  encode_segment "$out" \
    -ss "$start" -t "$duration" -i "$src" \
    -vf "$(video_filter)" \
    -map 0:v:0 -map 0:a:0? \
    -shortest
}

add_still() {
  local src="$1"
  local duration="$2"
  local out
  set_next_out
  out="$NEXT_OUT"

  echo "Adding still: $src for ${duration}s"
  encode_segment "$out" \
    -loop 1 -framerate "$FPS" -t "$duration" -i "$src" \
    -f lavfi -t "$duration" -i "anullsrc=channel_layout=stereo:sample_rate=$SR" \
    -vf "$(video_filter)" \
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

# Cold open
add_video "footage/01_Trip_Setup/001_IMG_0256_0142am_trip_setup.MOV" 0 8
add_video "footage/06_Car_Trouble_Return/048_IMG_0304_hotel_car_broke_down.MOV" 0 5
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 0 8
add_card 3 $'P056 PLACEHOLDER\nHand/key comparison flash'
add_card 6 $'I drove overnight for a keyboard\nmost pianists have never tried.'

# Setup
add_video "footage/08_Pickups_To_Record/055_PICKUP_front_facing_intro.MOV" 0 30
add_video "footage/01_Trip_Setup/001_IMG_0256_0142am_trip_setup.MOV" 41 13
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 49 23

# Overnight drive
add_video "footage/01_Trip_Setup/001_IMG_0256_0142am_trip_setup.MOV" 17 10
add_video "footage/01_Trip_Setup/002_IMG_0257_hagerstown_gas_station.MOV" 0 12
add_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 0 6
add_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 19 8
add_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 103 14
add_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 129 7
add_video "footage/02_Drive_To_Titusville/010_IMG_0266_drive_broll_2.MOV" 0 10
add_video "footage/01_Trip_Setup/005_IMG_0260_waking_up_after_car_nap.MOV" 0 8
add_video "footage/01_Trip_Setup/006_IMG_0261_car_nap_recovery_drive_resumes.MOV" 0 8
add_video "footage/01_Trip_Setup/006_IMG_0261_car_nap_recovery_drive_resumes.MOV" 29 7

# Pennsylvania road texture
add_video "footage/02_Drive_To_Titusville/007_IMG_0263_morning_highway_update.MOV" 21 23
add_video "footage/02_Drive_To_Titusville/008_IMG_0264_pennsylvania_scenery.MOV" 0 14
add_video "footage/02_Drive_To_Titusville/009_IMG_0265_drive_broll_1.MOV" 0 10
add_video "footage/02_Drive_To_Titusville/011_IMG_0267_in_the_woods_almost_there.MOV" 0 20
add_video "footage/02_Drive_To_Titusville/012_IMG_0268_double_big_mac_lunch.MOV" 0 4

# David's keyboard world
add_video "footage/03_David_Factory_Visit/013_IMG_0269_keyboard_21_intro.MOV" 0 7
add_video "footage/03_David_Factory_Visit/013_IMG_0269_keyboard_21_intro.MOV" 7 10
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 0 12
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 25 10
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 49 15
add_video "footage/03_David_Factory_Visit/019_IMG_0275_ds55_pickup_and_wrap.MOV" 0 10
add_video "footage/03_David_Factory_Visit/019_IMG_0275_ds55_pickup_and_wrap.MOV" 60 25
add_video "footage/03_David_Factory_Visit/027_IMG_0283_athena_internals_reconnaissance.MOV" 0 12
add_video "footage/03_David_Factory_Visit/027_IMG_0283_athena_internals_reconnaissance.MOV" 29 15
add_still "footage/04_Keyboards_Technical_Stills/030_IMG_0286_technical_keyboard_still.JPG" 3
add_still "footage/04_Keyboards_Technical_Stills/031_IMG_0287_technical_keyboard_still.JPG" 3
add_still "footage/04_Keyboards_Technical_Stills/032_IMG_0288_technical_keyboard_still.JPG" 3

# Main argument
add_card 3 "The real reason key size matters"
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 0 24
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 36 25
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 94 24
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 125 22
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 192 30

# The trip fights back
add_video "footage/05_Post_Pickup_Main_Argument/042_IMG_0298_tionesta_lake_cutaway.MOV" 0 9
add_video "footage/05_Post_Pickup_Main_Argument/043_IMG_0299_lake_overlook_broll.MOV" 0 12
add_video "footage/05_Post_Pickup_Main_Argument/044_IMG_0300_177777_mileage.MOV" 0 4
add_video "footage/06_Car_Trouble_Return/048_IMG_0304_hotel_car_broke_down.MOV" 0 20
add_video "footage/06_Car_Trouble_Return/048_IMG_0304_hotel_car_broke_down.MOV" 38 4
add_video "footage/06_Car_Trouble_Return/049_IMG_0305_car_fixed_heading_home.MOV" 0 19
add_video "footage/06_Car_Trouble_Return/050_IMG_0306_beautiful_return_drive.MOV" 0 8
add_video "footage/06_Car_Trouble_Return/053_IMG_0309_highway_home_broll.MOV" 0 12

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
