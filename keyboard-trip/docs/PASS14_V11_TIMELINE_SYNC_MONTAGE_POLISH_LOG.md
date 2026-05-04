# Pass 14 V11 Timeline Sync + Montage Polish Log

Output:

```text
keyboard-trip/renders/review_cuts/piano_hand_size_part2_rough_cut_v11.mp4
```

Runtime:

```text
12:48.69
```

Specs:

```text
1280x720, 30 fps, H.264 video, AAC audio, 148 MB
```

## Goals

- Repair source-of-truth drift between the editor SQLite timeline and
  the v10 render script.
- Keep Pass 13's creative structure, but remove the unnecessary
  last-frame holds added to every VO montage.
- Re-dump and validate the new pass before review.

## Diagnosis

Pass 13's render script had the intended cutaway structure, but the
SQLite pass did not fully match it:

- `p13-010-ds-size-lineup-setup` was ordered near the lake section in
  SQLite instead of right after VO_01c.
- Main-argument and home-payoff cutaways were ordered at the end of the
  pass in SQLite instead of between the A-roll chunks.
- VO_03 still reflected an older two-piece visual montage in SQLite,
  while the script used IMG_0261 still → waking video → IMG_0263 still.
- Music and VO rows had several stale explicit starts and durations.

Separately, Pass 13's `finish_montage_with_vo_and_music` helper used:

```text
max(video_duration, vo_duration) + 0.4
```

That defended against narration cutoffs, but it also added a 0.4s
last-frame hold to every montage even when the visual track already
covered the full VO.

## Changes Applied

### 1. Render helper polish

Cloned `make_rough_review_cut_v10.sh` to
`make_rough_review_cut_v11.sh`.

Changed the VO montage duration target to:

```text
max(video_duration, vo_duration + 0.4)
```

The cutoff defense remains, but v11 no longer freezes the last frame
when the visual montage is already long enough.

### 2. Pass 14 SQLite sync

Inserted:

- `pass-14-timeline-sync-montage-polish`
- `render-v11-timeline-sync-montage-polish`
- cloned Pass 13 timeline items with `p13` → `p14` ids

Then corrected the Pass 14 visual order to match the v11 script:

- VO_01a/b/c order is now linear.
- DS size-lineup setup is back immediately after VO_01c.
- Main-argument cutaways now sit between the car-monologue chunks.
- Home-payoff cutaways now sit between the home A-roll chunks.
- VO_03 now uses the same three visual pieces as the render script.

Also corrected explicit audio rows:

- cold-title music starts at `26.0`
- P056 cold-card music starts at `48.5`
- VO_01a/b/c, VO_02, VO_03, VO_04, VO_05, VO_06 source durations now
  match `ffprobe`
- music rows now cover the full visual montage windows

### 3. Asset metadata cleanup

Fixed three keyboard-still asset metadata paths so the dumped
`active_visual` source paths include the `footage/` prefix.

## Pass 13 → Pass 14 deltas

```text
render runtime:             771.99s → 768.69s
dumped timeline runtime:    763.5s  → 768.5s
enabled clips:              91      → 92
validation issues:          0       → 0
VO montage freeze holds:    yes     → only if VO requires extension
```

## Validation

```bash
python3 keyboard-trip/scripts/dump_timeline.py pass-14-timeline-sync-montage-polish --skip-contact-sheets
```

Result:

```text
[summary] 92 clips · 0 locked-by-user · 768.5s total
[issues] none
```

`ffprobe` on v11:

```text
duration=768.689563
video=H.264 1280x720 30fps
audio=AAC
```

## Known Rough Edges

- `056_PICKUP_hand_key_comparison.MOV` is still not recorded, so the
  cold-open and home-payoff placeholder cards remain.
- VO_02..VO_06 are still Cartesia TTS.
- VO_01a/b/c are still the existing split chunks; this pass did not
  regenerate or re-record narration.
- Talking-head buffers are still broad review-cut buffers rather than
  hand-trimmed final-master sentence tails.
