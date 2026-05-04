# Pass 10 V7 Flow + Music Log

Output:

```text
keyboard-trip/renders/review_cuts/piano_hand_size_part2_rough_cut_v7.mp4
```

Runtime:

```text
11:21
```

Specs:

```text
1280x720, 30 fps, H.264 video, AAC audio, 123 MB
```

## Goals

Address three review notes from Lionel:
- "Some clips don't make sense" — fix chronology so we don't show the
  destination before we've left.
- "Still images sit there" — cut the dragging slideshow at the end of the
  factory section and the duplicate stills.
- "We need to add in the music" — replace the procedural sine-drone
  placeholder with section-specific AI-generated music beds.

Also implements the new pre-pass discipline: this pass was planned from
`timelines/pass-9-real-vo-extended-montage.yaml` (the live SQLite snapshot)
and applied via the new `lastEditedBy` tracking — Pass 9 had zero
user-locked clips so the AI was free to recompose the whole timeline.

## Changes Applied

### Visual cuts (chronology + pacing)

- Removed `p9-002-home-payoff-flash` from the cold open. The home-payoff
  was holding for 8s as a flash-forward; strict chronology demanded
  cutting it entirely. The full home-payoff sequence still plays in its
  proper place at the end.
- Recomposed the VO_01 montage. Removed `p9-007-vo01-technical-still`
  (factory keyboard close-up) and `p9-009-vo01-ds-lineup` (DS lineup
  b-roll) — both showed end-of-trip content under "I was driving to
  Pennsylvania" narration. Replaced with night/early-trip imagery in
  chronological order:
  1. IMG_0256 selfie still (8s) — late-night setup
  2. IMG_0257 Hagerstown gas station still (6s)
  3. 004_IMG_0259 sheetz stop video (7s)
  4. IMG_0260 nap still (5s)
  5. 010_IMG_0266 rainy drive video (8s)
  6. IMG_0265 drive b-roll still (6s)
- Removed the 9-second slideshow of three keyboard close-up stills
  (`p9-038/039/040`) at the end of the factory section. The DS lineup
  b-roll above already establishes the visual case for the
  "key size matters" title card.
- Removed `p9-020-vo03-nap-still` — duplicate of the IMG_0260 still now
  used in the VO_01 montage. The VO_03 montage still uses IMG_0261
  (recovery still) and the morning-highway IMG_0263 still as bookends.

### Music — replace procedural drone with AI-generated beds

Generated four 60-second tracks via Replicate's Stable Audio 2.5 (each
~$0.05–0.10):

- `audio/music/ai_v1_late_night_drive_60s.mp3` — used under cold-open
  cards and VO_01 (late-night drive).
- `audio/music/ai_morning_road_60s.mp3` — used under VO_02, VO_03, VO_04
  (gas station, post-nap recovery, Pennsylvania road).
- `audio/music/ai_lake_pause_60s.mp3` — used under VO_05 (lake pause).
- `audio/music/ai_breakdown_return_60s.mp3` — used under VO_06
  (breakdown + return drive).

Volumes bumped: music_card 0.060 → 0.18, music_under_vo 0.055 → 0.16,
music_only 0.075 → 0.22. The procedural bed had been too quiet to
verify; with real composed-feeling beds the higher levels land cleaner.

`pass8_travel_bed.wav` and the procedural `ensure_music_bed` function
are no longer referenced. The script now pre-flights `ensure_music_beds`
that errors out if any of the four AI-generated files are missing.

## Mechanics

Pass 10 was created by:

1. Generating the three missing music files via
   `scripts/generate_music_bed.py "<prompt>" 60 <basename>`.
2. Writing `scripts/make_rough_review_cut_v7.sh` (cloned from v6 with
   the cuts and music routing applied).
3. Inserting the new `Pass 10` row, four music asset rows, and the
   `render-v7-flow-music` render-job row into SQLite.
4. Copying the Pass 9 timeline_items into Pass 10 with id rewrite,
   `lastEditedBy = 'ai'`, and `lastEditedAt = now()`.
5. Disabling the seven cut clips (`enabled = 0`) and inserting four new
   VO_01 montage rows for the chronology fix.
6. Re-pointing every Pass 10 music timeline row to its new
   section-specific asset.
7. Updating `projects.metadata.currentPass` /
   `currentPassId` / `currentRenderJobId`.
8. Re-running `dump_timeline.py pass-10-flow-and-music` →
   `timelines/pass-10-flow-and-music.yaml`. **Validation: zero issues.**

## Verification

```text
duration: 681.147500
video: h264, 1280x720, 30 fps
audio: aac, 48000 Hz, stereo
size: ~123 MB
```

Pass 9 → Pass 10 deltas:

```text
total runtime:    698s → 681s   (−17s from cold-open + slideshow cuts)
clips enabled:     81 →  78    (−7 cuts, +4 new VO_01 pieces)
music tracks:       1 →   4    (1 procedural drone → 4 AI-generated)
chronology issues:  3 →   0    (factory clips no longer in VO_01)
duplicate stills:   1 →   0    (IMG_0260 used once now)
```

## Known Rough Edges

- Cartesia narration on VO_02..VO_06 is still placeholder TTS (Lionel's
  real recording is only on VO_01).
- P056 hand/key comparison pickup is still a placeholder card.
- The new AI music beds are first-pass — if any specific section feels
  off, regenerate with a tightened prompt:
  `python3 scripts/generate_music_bed.py "<new prompt>" 60 <new_basename>`
  then re-point the relevant `asset-music-*` row in SQLite.
- Music tracks are 60s each but some sections (VO_01 montage at 40s,
  VO_06 at 17s) only need part of one track. Browser playback uses
  the start of each file; if a section needs a different feel, generate
  a different prompt rather than seeking into the existing file.
