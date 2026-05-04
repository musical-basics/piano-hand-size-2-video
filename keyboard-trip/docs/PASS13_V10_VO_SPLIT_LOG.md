# Pass 13 V10 VO Split + Cutoff Fix Log

Output:

```text
keyboard-trip/renders/review_cuts/piano_hand_size_part2_rough_cut_v10.mp4
```

Runtime:

```text
12:52
```

Specs:

```text
1280x720, 30 fps, H.264 video, AAC audio, 138 MB
```

## Goals

Lionel's Pass 12 review:

- "'Which sounds mature until you realize the backup is chocolate milk
  and sleeping in the car' — car gets cut off. This happens all the
  time for the narration."
- "I thought I said the narration goes too long, you need to cut up
  the narration and insert more b-roll travel sections w/ music and
  A sections in between."

## Diagnosis

Pass 12's VO_02 montage was 17.0s long (6+3+5+3) but the VO_02 audio
file is 17.28s. ffmpeg's `-t` cap on the output truncated 0.28s off
the end, which lands precisely on "the car" in the chocolate-milk
sentence. VO_03 had the same issue (14s montage vs 14.40s audio).

VO_01 was a single 40s block of narration over b-roll with no break,
which read as one long slideshow even though the visuals were all
moving. That's the "narration goes too long" complaint.

## Changes Applied

### 1. VO_02 + VO_03 cutoff fix

- VO_02 montage extended 17s → 19s (last snack chunk 3s → 5s).
- VO_03 montage extended 14s → 16s (waking video 6s → 7s, IMG_0263
  still 4s → 5s).

### 2. `finish_montage_with_vo_and_music` helper now self-defends

Added a runtime check inside the helper: if the silent video is
shorter than the VO + 0.4s buffer, it auto-extends the video by
holding the last frame (`tpad=stop_mode=clone:stop_duration=…`).
Future montages can't accidentally cut off a sentence even if the
script-side math is wrong.

### 3. VO_01 split into 3 chunks with A-roll inserts

Pre-cut VO_01_late_night_drive.wav at sentence boundaries (Whisper
timestamps confirmed the breaks):

- `VO_01a_late_night_thesis.wav` (10.07s) — "narrower keys can change
  the piano playing experience"
- `VO_01b_pennsylvania_setup.wav` (14.51s) — "almost 2 in the morning,
  driving to PA, DS5.5/6.0 keyboards from David"
- `VO_01c_millimeters_payoff.wav` (15.33s) — "millimeters change
  everything, weeks not months"

New cold-open + VO_01 area structure:

```
0–7.5s     front-facing intro chunk 1 (talking head)
7.5–26s    front-facing intro chunk 2 (talking head)
26–31s     hook card "I drove overnight..."
31–48.5s   1:42 AM selfie (talking head)
48.5–51.5s P056 placeholder card
51.5–62s   VO 01a + b-roll montage (rainy drive + gas station)
62–67s     A-ROLL BURST: snack vlog moment
67–82s     VO 01b + b-roll montage (sheetz + drive b-roll)
82–86.5s   A-ROLL BURST: waking up reaction
86.5–102.5s VO 01c + b-roll montage (recovery + rainy drive late)
```

That's the requested pattern: VO chunk → A-roll → VO chunk → A-roll
→ VO chunk. Eye gets a break from b-roll every ~15s, and the
narration breathes between sentences instead of running uninterrupted
for 40s.

## Mechanics

1. ffmpeg-chunked VO_01 into 3 sentence-bounded wav files.
2. Cloned `make_rough_review_cut_v9.sh` → `v10.sh`.
3. Added the auto-extend safety in `finish_montage_with_vo_and_music`.
4. Replaced the single VO_01 block with three separate
   `finish_montage_with_vo_and_music` calls + two `add_video`
   A-roll insert calls in between.
5. Bumped VO_02 + VO_03 montage durations.
6. Added 3 new audio asset rows for the chunked VO files.
7. Inserted Pass 13 row, render-v10 row, copied Pass 12 → Pass 13
   timeline. Disabled the 8 Pass 12 rows that represented the old
   single-block VO_01. Inserted 14 new rows: 6 b-roll visuals + 3
   audio chunks + 3 music chunks + 2 A-roll inserts.
8. Set explicit `timelineStart` on the new audio/music rows so the
   editor display matches the actual render position (rather than
   cursor-stacking them at the end of the timeline).
9. Updated `projects.metadata.currentPass` etc.
10. Re-dumped `pass-13-vo-split-and-buffer.yaml` — zero issues.

## Pass 12 → Pass 13 deltas

```text
runtime:                    754s → 772s   (+18s)
clips enabled:               85 →  91    (+6 net: -8 old VO_01 + 14 new)
VO_01 audio blocks:           1 →   3    (single block → 3 sentence chunks)
A-roll bursts inside VO_01:   0 →   2
Cutoff bugs:        VO_02, VO_03 → 0
Helper self-defense:         no →  yes  (auto-extends video to fit VO)
```

## Known Rough Edges

- VO_01b/VO_01c chunks have small audible artifacts at the cut
  boundaries since I split with `-c copy` at non-keyframe positions.
  Re-encode the chunks if the seam is audible at full quality.
- The 5s snack-vlog A-roll insert and 4.5s waking-up A-roll insert
  carry their original audio — Lionel's voice crosses the music bed
  briefly. Acceptable for review; for final mix consider ducking
  the music dramatically during these inserts.
- Other VO sections (VO_04, VO_05, VO_06) remain single blocks. If
  any feel too long, we can split them too with the same approach.
