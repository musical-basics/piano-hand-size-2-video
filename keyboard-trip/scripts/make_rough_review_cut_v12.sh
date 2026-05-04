#!/usr/bin/env bash
set -euo pipefail

# Always run from the keyboard-trip root
cd "$(dirname "$0")/.."

OUT_DIR="renders/review_cuts"
OUT_FILE="$OUT_DIR/piano_hand_size_part2_rough_cut_v12.mp4"
WORK_DIR="$(mktemp -d /private/tmp/piano-hand-size-rough-cut-v12.XXXXXX)"
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
MUSIC_CARD_VOLUME="0.28"
MUSIC_UNDER_VO_VOLUME="0.24"
MUSIC_ONLY_VOLUME="0.36"

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

caption_filter() {
  local rotate="${1:-none}"
  local text_file="$2"
  printf "%s,drawbox=x=76:y=560:w=1128:h=104:color=black@0.62:t=fill,drawtext=fontfile=%s:textfile=%s:fontcolor=white:fontsize=34:line_spacing=8:x=(w-text_w)/2:y=586" \
    "$(video_filter "$rotate")" "$FONT" "$text_file"
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
  local out fade_start
  set_next_out
  out="$NEXT_OUT"
  # Audio fade-out 0.4s before clip end so a-roll cuts feel smooth, not chopped.
  fade_start="$(awk -v d="$duration" 'BEGIN { v=d-0.4; if (v<0) v=0; printf "%.3f", v }')"

  echo "Adding video: $src @ $start for ${duration}s rotation=${rotate}"
  encode_segment "$out" \
    -ss "$start" -t "$duration" -i "$src" \
    -vf "$(video_filter "$rotate")" \
    -af "afade=t=out:st=${fade_start}:d=0.4" \
    -map 0:v:0 -map 0:a:0? \
    -shortest
}

add_video_captioned() {
  local src="$1"
  local start="$2"
  local duration="$3"
  local rotate="$4"
  local caption="$5"
  local out fade_start text_file
  set_next_out
  out="$NEXT_OUT"
  text_file="$WORK_DIR/caption_${segment_index}.txt"
  printf "%s\n" "$caption" > "$text_file"
  fade_start="$(awk -v d="$duration" 'BEGIN { v=d-0.4; if (v<0) v=0; printf "%.3f", v }')"

  echo "Adding captioned video: $src @ $start for ${duration}s rotation=${rotate}"
  encode_segment "$out" \
    -ss "$start" -t "$duration" -i "$src" \
    -vf "$(caption_filter "$rotate" "$text_file")" \
    -af "afade=t=out:st=${fade_start}:d=0.4" \
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
    -filter_complex "[1:a]aresample=${SR},loudnorm=I=-16:LRA=11:TP=-1.5[vo]" \
    -map 0:v:0 -map "[vo]" \
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
  local caption="${3:-}"
  local silent_video="$MONTAGE_DIR/silent_video.mp4"
  local out montage_duration fade_out_start vo_duration video_duration target_duration text_file
  set_next_out
  out="$NEXT_OUT"

  echo "Finishing VO+music montage: $label with $vo"
  ffmpeg -y -hide_banner -loglevel error \
    -f concat -safe 0 -i "$MONTAGE_CONCAT" \
    -c copy \
    "$silent_video"

  # Defense against the v8/v9 cut-off bug: if the VO is longer than the
  # silent visual track, extend the video by holding the last frame so the
  # full sentence can finish. Keep planned visual length when it already
  # covers the VO plus a 0.4s buffer.
  video_duration="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$silent_video")"
  vo_duration="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$vo")"
  target_duration="$(awk -v v="$video_duration" -v a="$vo_duration" 'BEGIN { a=a+0.4; printf "%.3f", (v>a?v:a) }')"
  if awk -v t="$target_duration" -v v="$video_duration" 'BEGIN { exit !(t > v + 0.05) }'; then
    local hold_for
    hold_for="$(awk -v t="$target_duration" -v v="$video_duration" 'BEGIN { printf "%.3f", t - v }')"
    echo "  extending silent video by ${hold_for}s (video=${video_duration}s, vo=${vo_duration}s)"
    local extended="$MONTAGE_DIR/silent_video_extended.mp4"
    ffmpeg -y -hide_banner -loglevel error \
      -i "$silent_video" \
      -vf "tpad=stop_mode=clone:stop_duration=${hold_for}" \
      -c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p \
      -an "$extended"
    silent_video="$extended"
  fi
  montage_duration="$target_duration"
  fade_out_start="$(awk -v d="$montage_duration" 'BEGIN { v=d-1.2; if (v<0) v=0; printf "%.3f", v }')"

  # VO normalised to -16 LUFS (single-pass loudnorm) so all narration sits
  # at the same perceived loudness regardless of source — Cartesia TTS and
  # Lionel's Logic-bounced VO_01 land at very different levels otherwise.
  if [ -n "$caption" ]; then
    text_file="$WORK_DIR/caption_${segment_index}.txt"
    printf "%s\n" "$caption" > "$text_file"
    ffmpeg -y -hide_banner -loglevel error \
      -i "$silent_video" -i "$vo" -stream_loop -1 -i "$MUSIC_BED" \
      -filter_complex "[0:v]$(caption_filter none "$text_file")[v];[1:a]aresample=${SR},loudnorm=I=-16:LRA=11:TP=-1.5,apad=whole_dur=${montage_duration}[vo];[2:a]aresample=${SR},volume=${MUSIC_UNDER_VO_VOLUME},atrim=0:${montage_duration},afade=t=in:st=0:d=0.8,afade=t=out:st=${fade_out_start}:d=1.2[music];[vo][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[a]" \
      -map "[v]" -map "[a]" \
      -c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p \
      -c:a aac -b:a 160k -ar "$SR" -ac 2 \
      -t "$montage_duration" \
      -movflags +faststart \
      "$out"
  else
    ffmpeg -y -hide_banner -loglevel error \
      -i "$silent_video" -i "$vo" -stream_loop -1 -i "$MUSIC_BED" \
      -filter_complex "[1:a]aresample=${SR},loudnorm=I=-16:LRA=11:TP=-1.5,apad=whole_dur=${montage_duration}[vo];[2:a]aresample=${SR},volume=${MUSIC_UNDER_VO_VOLUME},atrim=0:${montage_duration},afade=t=in:st=0:d=0.8,afade=t=out:st=${fade_out_start}:d=1.2[music];[vo][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[a]" \
      -map 0:v:0 -map "[a]" \
      -c:v copy \
      -c:a aac -b:a 160k -ar "$SR" -ac 2 \
      -t "$montage_duration" \
      -movflags +faststart \
      "$out"
  fi
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

# Pass 12: extended every talking-head clip's duration by 1-1.5s so
# Lionel's sentences finish before each cut, plus a 0.4s audio fade-out
# in add_video. Pass 11 routinely cut him off mid-word.
add_video_captioned "footage/08_Pickups_To_Record/055_PICKUP_front_facing_intro.MOV" 0 7.5 none $'Piano Hand Size, Part 2'
add_video_captioned "footage/08_Pickups_To_Record/055_PICKUP_front_facing_intro.MOV" 13.5 18.5 none $'I drove overnight for smaller piano keys.'

# Hook card right after the intro promise.
MUSIC_BED="$MUSIC_LATE_NIGHT"
add_card_with_music 5 $'I drove overnight for a keyboard\nmost pianists have never tried.'

# 1:42 AM setup — the proof of the trip's commitment.
add_video_captioned "footage/01_Trip_Setup/001_IMG_0256_0142am_trip_setup.MOV" 0 17.5 none $'1:42 AM\nBaltimore to Titusville, Pennsylvania'

# Hand/key comparison placeholder (waiting on P056 pickup).
add_card_with_music 3 $'P056 PLACEHOLDER\nHand/key comparison flash'

# VO_01 split into 3 chunks at sentence boundaries with quick A-roll
# inserts in between. Pass 12 had 40s of uninterrupted VO + b-roll which
# felt like a slideshow; Pass 13 alternates: VO+broll → A-roll → VO+broll
# → A-roll → VO+broll. Mr Beast vlog energy.

# VO_01a (10s): "narrower keys can change the piano playing experience"
MUSIC_BED="$MUSIC_LATE_NIGHT"
start_montage
montage_piece_video "footage/02_Drive_To_Titusville/010_IMG_0266_drive_broll_2.MOV" 0 5
montage_piece_video "footage/01_Trip_Setup/002_IMG_0257_hagerstown_gas_station.MOV" 7 5.5 cw
finish_montage_with_vo_and_music "audio/voiceovers/VO_01a_late_night_thesis.wav" "VO 01a thesis" $'Narrower keys can change the whole\npiano-playing experience.'

# A-roll burst: snack vlog moment (different chunk than the post-VO_02 use)
add_video_captioned "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 30 5 none $'Road-trip fuel'

# VO_01b (14.5s): "almost 2 in the morning, driving to PA, DS5.5/6.0 keyboards from David"
MUSIC_BED="$MUSIC_LATE_NIGHT"
start_montage
montage_piece_video "footage/01_Trip_Setup/004_IMG_0259_sheets_stop_middle_of_nowhere.MOV" 0 7
montage_piece_video "footage/02_Drive_To_Titusville/009_IMG_0265_drive_broll_1.MOV" 7 8
finish_montage_with_vo_and_music "audio/voiceovers/VO_01b_pennsylvania_setup.wav" "VO 01b PA setup" $'Almost 2 AM: driving to Pennsylvania\nfor DS 5.5 and DS 6.0 keyboards.'

# A-roll burst: waking up reaction
add_video_captioned "footage/01_Trip_Setup/005_IMG_0260_waking_up_after_car_nap.MOV" 8 4.5 none $'The car nap begins'

# VO_01c (15.3s): "millimeters change everything, weeks not months"
MUSIC_BED="$MUSIC_LATE_NIGHT"
start_montage
montage_piece_video "footage/01_Trip_Setup/006_IMG_0261_car_nap_recovery_drive_resumes.MOV" 14 7
montage_piece_video "footage/02_Drive_To_Titusville/010_IMG_0266_drive_broll_2.MOV" 15 9
finish_montage_with_vo_and_music "audio/voiceovers/VO_01c_millimeters_payoff.wav" "VO 01c millimeters" $'A few millimeters on each key\ncan change everything.'

# Keep the travel chronology intact: no David/workshop footage appears until
# after the gas-station, snack, nap, morning-drive, woods, and lunch beats.

# VO 02 Gas Station And Snacks (17.28s VO). Montage extended to 19s so
# "chocolate milk and sleeping in the car" finishes — the v9 cutoff bug.
MUSIC_BED="$MUSIC_MORNING"
start_montage
montage_piece_video "footage/01_Trip_Setup/002_IMG_0257_hagerstown_gas_station.MOV" 0 6 cw
montage_piece_still "footage/90_Reference_Frames/IMG_0258.jpg" 3
montage_piece_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 103 5
montage_piece_video "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 19 5
finish_montage_with_vo_and_music "audio/voiceovers/VO_02_gas_station_and_snacks.wav" "VO 02 gas station and snacks" $'Gas stations, snacks,\nand questionable decisions.'

# Preserve the snack/car-nap vlog beats with original audio after VO.
add_video_captioned "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 0 7.5 none $'No caffeine.'
add_video_captioned "footage/01_Trip_Setup/003_IMG_0258_road_trip_snacks_no_caffeine.MOV" 19 6.5 none $'Backup plan: chocolate milk.'

# Nap section a-roll.
add_video_captioned "footage/01_Trip_Setup/005_IMG_0260_waking_up_after_car_nap.MOV" 0 7.5 none $'A few hours later'
add_video_captioned "footage/01_Trip_Setup/006_IMG_0261_car_nap_recovery_drive_resumes.MOV" 0 6.5 none $'Almost three hours of sleep'
add_video_captioned "footage/01_Trip_Setup/006_IMG_0261_car_nap_recovery_drive_resumes.MOV" 29 5.5 none $'Back on the road'

# VO 03 Car Nap (14.40s VO). Montage extended to 16s for the same buffer
# reason as VO_02. Auto-extend in finish_montage_with_vo_and_music is the
# safety net but explicit padding keeps cuts on visual beats.
MUSIC_BED="$MUSIC_MORNING"
start_montage
montage_piece_still "footage/90_Reference_Frames/IMG_0261.jpg" 4
montage_piece_video "footage/01_Trip_Setup/005_IMG_0260_waking_up_after_car_nap.MOV" 6 7
montage_piece_still "footage/90_Reference_Frames/IMG_0263.jpg" 5
finish_montage_with_vo_and_music "audio/voiceovers/VO_03_car_nap.wav" "VO 03 car nap" $'Slept in the car.\nHuman enough to keep driving.'

# Pennsylvania road texture — VO 04 keeps its current visuals.
add_video_captioned "footage/02_Drive_To_Titusville/007_IMG_0263_morning_highway_update.MOV" 21 11.5 none $'Morning update:\n3.5 hours to go'
MUSIC_BED="$MUSIC_MORNING"
start_montage
montage_piece_video "footage/02_Drive_To_Titusville/008_IMG_0264_pennsylvania_scenery.MOV" 0 8
montage_piece_video "footage/02_Drive_To_Titusville/009_IMG_0265_drive_broll_1.MOV" 0 7
montage_piece_still "footage/90_Reference_Frames/IMG_0267.jpg" 5
finish_montage_with_vo_and_music "audio/voiceovers/VO_04_pennsylvania_road.wav" "VO 04 Pennsylvania road" $'By morning, Pennsylvania\nstarted to feel real.'
add_video_captioned "footage/02_Drive_To_Titusville/011_IMG_0267_in_the_woods_almost_there.MOV" 0 13.5 none $'After five hours:\n48 minutes left'
add_video_captioned "footage/02_Drive_To_Titusville/012_IMG_0268_double_big_mac_lunch.MOV" 0 5 none $'Emergency lunch'

# David's keyboard world. Rotations applied from review notes. Talking-head
# durations bumped 1.5s for sentence-tail buffer.
add_video_captioned "footage/03_David_Factory_Visit/013_IMG_0269_keyboard_21_intro.MOV" 0 8.5 none $'Arrived:\nDavid Steinbuhler workshop'
add_video "footage/03_David_Factory_Visit/013_IMG_0269_keyboard_21_intro.MOV" 7 11.5
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 0 13.5 ccw
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 25 11.5 ccw
add_video "footage/03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV" 49 16.5 ccw
add_video "footage/03_David_Factory_Visit/019_IMG_0275_ds55_pickup_and_wrap.MOV" 0 11.5
add_video "footage/03_David_Factory_Visit/019_IMG_0275_ds55_pickup_and_wrap.MOV" 60 26.5
add_video "footage/03_David_Factory_Visit/027_IMG_0283_athena_internals_reconnaissance.MOV" 0 13.5 ccw
add_video "footage/03_David_Factory_Visit/027_IMG_0283_athena_internals_reconnaissance.MOV" 29 16.5 ccw

# Main argument: 5 chunks of the car monologue with b-roll cutaways
# inserted between every chunk so the eye gets a break from the talking
# head every ~25s. Each cutaway is 3-4s of keyboard b-roll.
add_card 3 "The real reason key size matters"
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 0 25.5
add_still "footage/04_Keyboards_Technical_Stills/030_IMG_0286_technical_keyboard_still.JPG" 3 ccw
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 36 26.5
add_still "footage/04_Keyboards_Technical_Stills/031_IMG_0287_technical_keyboard_still.JPG" 3 ccw
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 94 25.5
add_still "footage/04_Keyboards_Technical_Stills/032_IMG_0288_technical_keyboard_still.JPG" 3 ccw
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 125 23.5
add_video "footage/03_David_Factory_Visit/019_IMG_0275_ds55_pickup_and_wrap.MOV" 30 4
add_video "footage/05_Post_Pickup_Main_Argument/041_IMG_0297_ds60_ds55_car_monologue.MOV" 192 31.5

# The trip fights back. Lake gets VO 05 with the contemplative lake_pause
# bed; mileage extended from 4s to 6s.
MUSIC_BED="$MUSIC_LAKE"
start_montage
montage_piece_video "footage/05_Post_Pickup_Main_Argument/042_IMG_0298_tionesta_lake_cutaway.MOV" 0 7
montage_piece_video "footage/05_Post_Pickup_Main_Argument/043_IMG_0299_lake_overlook_broll.MOV" 0 7
montage_piece_video "footage/05_Post_Pickup_Main_Argument/044_IMG_0300_177777_mileage.MOV" 0 6
montage_piece_still "footage/90_Reference_Frames/IMG_0300.jpg" 2
finish_montage_with_vo_and_music "audio/voiceovers/VO_05_lake_pause.wav" "VO 05 lake pause" $'After visiting David,\nI stopped by the lake to breathe.'

# Breakdown + return — unresolved-tension music for the saga arc.
add_video "footage/06_Car_Trouble_Return/048_IMG_0304_hotel_car_broke_down.MOV" 0 9.5
MUSIC_BED="$MUSIC_BREAKDOWN"
start_montage
montage_piece_still "footage/90_Reference_Frames/IMG_0304.jpg" 4
montage_piece_video "footage/06_Car_Trouble_Return/049_IMG_0305_car_fixed_heading_home.MOV" 0 8
montage_piece_video "footage/06_Car_Trouble_Return/050_IMG_0306_beautiful_return_drive.MOV" 0 6
montage_piece_video "footage/06_Car_Trouble_Return/053_IMG_0309_highway_home_broll.MOV" 0 8
finish_montage_with_vo_and_music "audio/voiceovers/VO_06_breakdown_and_return.wav" "VO 06 breakdown and return" $'The car broke down in Pennsylvania.\nThe trip had one more plot twist.'

# Home payoff. Talking-head durations bumped 1.5s. B-roll cutaways
# (3-4s keyboard stills) inserted between long chunks so the eye gets a
# break from the same talking-head shot.
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 0 21.5
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 43 19.5
add_card 5 $'P056 PLACEHOLDER\nStandard vs DS 6.0 vs DS 5.5'
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 71 25.5
add_still "footage/04_Keyboards_Technical_Stills/034_IMG_0290_technical_keyboard_still.JPG" 3 ccw
add_card 5 $'My current take\nTry DS 6.0 and DS 5.5 if possible.\nUnder ~8.2 inches: consider DS 5.5 too.'
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 126 13.5
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 154 19.5
add_still "footage/04_Keyboards_Technical_Stills/036_IMG_0292_technical_keyboard_still.JPG" 3 ccw
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 178 19.5
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 221 36.5
add_still "footage/04_Keyboards_Technical_Stills/038_IMG_0294_technical_keyboard_still.JPG" 3 ccw
add_video "footage/07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.MOV" 296 14.5
add_card 7 $'Part 3:\nDS 6.0 vs DS 5.5 comparison?'

echo "Concatenating segments..."
ffmpeg -y -hide_banner -loglevel error \
  -f concat -safe 0 -i "$CONCAT_FILE" \
  -c copy \
  "$OUT_FILE"

echo "Wrote $OUT_FILE"
echo "Temporary segment workdir: $WORK_DIR"
