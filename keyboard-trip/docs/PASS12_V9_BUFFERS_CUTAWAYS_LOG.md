# Pass 12 V9 Buffers + Cutaways + Upbeat Music Log

Output:

```text
keyboard-trip/renders/review_cuts/piano_hand_size_part2_rough_cut_v9.mp4
```

Runtime:

```text
12:34
```

Specs:

```text
1280x720, 30 fps, H.264 video, AAC audio, 139 MB
```

## Goals

Lionel's Pass 11 review:

- "A lot of times the audio is cut off when I'm talking. You need to
  leave more buffer between the end of clips."
- "The narration sometimes goes too long. It needs to cut more between
  live action shots and b-roll."
- "The music should be more upbeat. This is too dreamy and slow."

## Changes Applied

### 1. Talking-head buffers (+1.5s on every a-roll where Lionel speaks)

Bumped the duration of every a-roll talking-head clip by ~1.5s so
sentences finish before each cut. 34 clips affected:

- Cold-open intro chunks: 6 → 7.5s, 17 → 18.5s
- 1:42 AM selfie: 16 → 17.5s
- Snack vlog beats, nap sequence, woods/big-mac: each +1.5s
- Factory section talking heads (4 keyboard explanations,
  pickup-and-wrap, athena internals): +1.5s each
- Main argument car monologue (5 chunks): +1.5s each
- Home payoff (8 chunks): +1.5s each

Plus a 0.4s audio fade-out applied at the end of every `add_video`
segment so even when the cut still lands inside a sentence, the cut
sounds tapered instead of chopped.

Total duration impact: ~+50s.

### 2. B-roll cutaways inside long talking sections

The main argument was 5 chunks of the same talking-head shot totalling
~125s of "Lionel in the car." Pass 12 cuts away to keyboard b-roll
between every chunk:

- Main argument chunk 1 → IMG_0286 keyboard close-up still (3s ccw)
- Main argument chunk 2 → IMG_0287 keyboard close-up still (3s ccw)
- Main argument chunk 3 → IMG_0288 keyboard close-up still (3s ccw)
- Main argument chunk 4 → 019_IMG_0275 DS55 pickup b-roll (4s)
- Main argument chunk 5

Same treatment applied to home payoff:

- Home chunk 3 → IMG_0290 keyboard still (3s ccw)
- Home chunk 5 → IMG_0292 keyboard still (3s ccw)
- Home chunk 7 → IMG_0294 keyboard still (3s ccw)

Total duration impact: 7 cutaways × ~3.3s avg = ~23s added.

### 3. Upbeat music regeneration

All four AI-generated music beds regenerated via Replicate Stable Audio
2.5 with explicitly upbeat indie/vlog prompts:

- `ai_v1_late_night_drive_60s.mp3` —
  "upbeat indie pop instrumental, plucky acoustic guitar with light
  percussion claps and shaker, driving forward energy, 110 bpm,
  optimistic travel vlog music, hopeful and bright"
- `ai_morning_road_60s.mp3` —
  "energetic indie folk pop, fingerpicked acoustic guitar with hand
  claps, tambourine, joyful upbeat momentum, 120 bpm, vlog travel
  music, sunshine and motion"
- `ai_lake_pause_60s.mp3` —
  "warm acoustic interlude, gentle fingerpicked guitar with soft piano
  and shaker, brief breath in the journey, 90 bpm, indie folk vlog
  reflection, light and hopeful"
- `ai_breakdown_return_60s.mp3` —
  "indie pop instrumental, building from quiet to triumphant, light
  drums kicking in midway, hopeful resolution, 105 bpm, cinematic vlog
  music, melancholy lifting to optimism"

The earlier prompts used "ambient / cinematic / atmospheric / pads"
which the model interpreted as slow synth drone. New prompts emphasize
"plucky acoustic guitar / claps / hand percussion / drums / bpm in the
100s" — closer to a vlog soundtrack than a meditation track.

Same file paths, so no DB asset changes; the editor's audio mixer
picks up the new files automatically.

## Mechanics

1. Deleted the four old `ai_*_60s.mp3` files.
2. Regenerated each via `scripts/generate_music_bed.py` with new
   upbeat prompts. ~$0.40 of Replicate credit total.
3. Cloned `make_rough_review_cut_v8.sh` → `v9.sh`.
4. Bumped 34 talking-head durations in the script.
5. Inserted 4 main-argument cutaways and 3 home-payoff cutaways.
6. Added `-af afade=t=out:st=...:d=0.4` to every `add_video` call.
7. Inserted Pass 12 row, render-v9 row, copied Pass 11 timeline →
   Pass 12, applied 34 duration UPDATEs and 7 cutaway INSERTs in
   SQLite via a Python script.
8. Created three missing asset rows for IMG_0290/0292/0294.
9. Updated `projects.metadata.currentPass` etc.
10. Re-dumped `pass-12-buffers-cutaways.yaml` — zero validation
    issues.

## Pass 11 → Pass 12 deltas

```text
runtime:                    681s → 754s   (+73s — buffers + cutaways)
clips enabled:               78 →  85    (+7 cutaway clips)
talking-head clips bumped:    0 →  34    (each +1.5s)
audio fade-out on a-roll:    no → yes    (0.4s tail)
music character:        ambient → upbeat indie/folk
chronology issues:            0 →   0
```

## Known Rough Edges

- Cartesia narration on VO_02..VO_06 still has the AI-voice character;
  the seam between Lionel's real VO_01 and the cloned VO_02 audible.
- P056 hand/key comparison pickup is still a placeholder card.
- Some +1.5s buffers may overshoot the natural sentence end (silent
  tail before next cut). Acceptable for review; for final master
  trim each clip's exact end manually after listening.
- Stable Audio 2.5 ignores BPM/instrument prompts inconsistently;
  if a regenerated track still feels too dreamy, regen it with an
  even more genre-specific prompt (e.g. "lo-fi hip-hop" or
  "alt rock instrumental").
