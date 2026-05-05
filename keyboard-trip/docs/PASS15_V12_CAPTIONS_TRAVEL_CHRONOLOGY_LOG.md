# Pass 15 V12 Captions + Travel Chronology Log

Output:

```text
keyboard-trip/renders/review_cuts/piano_hand_size_part2_rough_cut_v12.mp4
```

Runtime:

```text
12:32.79
```

Specs:

```text
1280x720, 30 fps, H.264 video, AAC audio, 140 MB
```

## Goals

Lionel's review note:

- "start adding captions"
- "the chronology of the travel time to david's place is still not right"
- "re-review the various parts and what i'm saying in each narration vs.
  the actual scenes"
- "i can't even hear the background music anymore"

## Diagnosis

The main chronology problem was the early David/workshop reveal:

```text
VO_01c ends around 1:42, then Pass 14 immediately showed
018_IMG_0274_ds_size_lineup_on_steinway.MOV.
```

That made the cut visually arrive at David's before the gas-station,
snack, car-nap, morning-drive, woods, and lunch beats had happened.
It also made VO_02/VO_03/VO_04 feel like flashbacks even though their
language describes the ongoing trip.

Reviewed travel narration against scene order:

- VO_01a/b/c: thesis and "driving to Pennsylvania" setup, so it stays
  on road/gas/Sheetz/recovery-drive visuals only.
- VO_02: gas stations, snacks, chocolate milk, sleeping in the car, so
  it now directly leads into the snack and nap A-roll.
- VO_03: car nap and waking up, so it stays on sleep/recovery/morning
  visuals.
- VO_04: "By morning" and "getting close", so it stays on morning
  highway, Pennsylvania scenery, and woods/48-minutes-left visuals.
- David/workshop footage now starts only after the woods and lunch
  beats.

## Changes Applied

### 1. Travel chronology fixed

Removed the early pre-arrival DS size-lineup reveal from the travel
section. The same DS lineup proof still appears in the David section
after arrival.

New travel-to-David order:

```text
1:42 AM setup
P056 placeholder flash
VO_01a road/gas
snack burst
VO_01b Sheetz/drive
car-nap burst
VO_01c recovery/rainy drive
VO_02 gas/snacks/chocolate milk
snack A-roll
car-nap/recovery A-roll
VO_03 car nap
morning highway update: 3.5 hours to go
VO_04 Pennsylvania roads
woods: 48 minutes left
Double Big Mac
David's workshop arrival
```

### 2. First caption layer added

Added burned-in caption support to `make_rough_review_cut_v12.sh`:

- `caption_filter`
- `add_video_captioned`
- optional caption argument on `finish_montage_with_vo_and_music`

This is a first-pass caption layer, not full word-for-word subtitles.
It covers the opening/travel narration, travel checkpoint A-roll, lake
VO, and breakdown VO. A captioned frame was spot-checked at `00:02:55`
and the text box rendered cleanly.

### 3. Music made audible again

Raised render music constants:

```text
MUSIC_CARD_VOLUME       0.18 -> 0.28
MUSIC_UNDER_VO_VOLUME   0.16 -> 0.24
MUSIC_ONLY_VOLUME       0.22 -> 0.36
```

Also changed VO/music mixing from ffmpeg's default normalized `amix` to
`normalize=0` with an `alimiter`, so the music bed no longer gets
silently halved during VO montages.

Quick loudness spot-check on the gas-station/snacks VO section:

```text
v11 comparable section: -20.2 LUFS integrated
v12 comparable section: -16.8 LUFS integrated
```

## Pass 14 -> Pass 15 Deltas

```text
render runtime:             768.69s -> 752.79s
dumped timeline runtime:    768.5s  -> 752.5s
enabled clips:              92      -> 91
validation issues:          0       -> 0
early David reveal:         yes     -> no
caption layer:              no      -> starter burned-in captions
VO/music mix:               subdued -> louder, limited mix
```

## Validation

```bash
python3 keyboard-trip/scripts/dump_timeline.py pass-15-captions-travel-chronology --skip-contact-sheets
```

Result:

```text
[summary] 91 clips, 0 locked-by-user, 752.5s total
[issues] none
```

`ffprobe` on v12:

```text
duration=752.788000
video=H.264 1280x720 30fps
audio=AAC
```

## FCPXML Import Notes

The raw-source Final Cut XML debugging found one repeatable crash source:
JPG stills imported as `<asset-clip>` timeline items. The failing media
diagnostics were `IMG_0258.jpg` and `IMG_0260.jpg` in the 11-15 media
range. Exporting those same source JPG assets as `<video>` timeline items
fixed the crash while keeping the clips linked to the original source files.

Use the raw-native timeline-rotations export for Final Cut handoff:

```bash
python3 keyboard-trip/scripts/export_fcpxml.py pass-15-captions-travel-chronology \
  --output keyboard-trip/exports/fcpxml/piano_hand_size_part2_pass15_v12_raw_native_timeline_rotations.fcpxml
```

Keep `normalized-clips` / `segments` only as rescue exports. They import
cleanly, but they intentionally point FCP at generated intermediates instead
of the raw source media.

The actual multilane edit export is the better FCP handoff now that the raw
source diagnostics pass:

```bash
python3 keyboard-trip/scripts/export_fcpxml.py pass-15-captions-travel-chronology \
  --timeline-mode connected-gap \
  --title-mode native \
  --force-clip-rotation 042_IMG_0298_tionesta_lake_cutaway.MOV=270 \
  --output keyboard-trip/exports/fcpxml/piano_hand_size_part2_pass15_v12_actual_edit_multilane_native_titles.fcpxml
```

For future round-trip import back into Cut Notes, the exporter now writes
stable breadcrumbs into FCPXML: `cutnotes.*` metadata on asset resources and
metadata-capable timeline items, plus `note` payloads prefixed with
`cutnotes:` on timeline elements where FCPXML does not allow metadata. The
importer should treat SQLite as the app source format, prefer
`cutnotes.timelineItemId` / `cutnotes.assetId`, and fall back to parsing the
note JSON if Final Cut strips formal metadata.

Rotation diagnostics showed that MOV display-matrix metadata alone cannot
determine semantic orientation. `019_IMG_0275_ds55_pickup_and_wrap.MOV` and
`042_IMG_0298_tionesta_lake_cutaway.MOV` both report `rotation=-90`, but
`019` is correct when FCP uses only the camera display matrix, while `042`
needs an additional `270` timeline/XML rotation. Use existing timeline
rotations when they exist (`018` / `027`), and for unmarked sideways clips
generate 0/90/180/270 probes and judge them visually from faces, horizons,
keyboards, and readable labels. Known current finding: `042` is correct at
`270`.

## Known Rough Edges

- Captions are starter/summary captions, not full word-for-word
  subtitles yet.
- `056_PICKUP_hand_key_comparison.MOV` is still not recorded, so the
  cold-open and home-payoff placeholder cards remain.
- VO_02..VO_06 are still Cartesia TTS.
- Talking-head buffers are still broad review-cut buffers rather than
  hand-trimmed final-master sentence tails.
