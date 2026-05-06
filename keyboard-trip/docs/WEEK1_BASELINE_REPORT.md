# Week 1 Baseline Report

Generated: 2026-05-06

What the Week-1 deterministic stack found when it was first pointed at
the current cut (Pass 15: Captions + Travel Chronology). This is the
baseline we measure against as Week 2+ work lands.

## Stack run

```bash
python3 scripts/dump_timeline.py pass-15-captions-travel-chronology
python3 scripts/export_ai_timeline_brief.py pass-15-captions-travel-chronology
python3 scripts/validate_timeline_semantics.py pass-15-captions-travel-chronology
```

## Pass 15 snapshot

- Runtime: 752.5s (12:32)
- Clips (enabled): 91
- Active visual segments: 73
- Locked-by-user clips: 0
- Issues from `dump_timeline.py`: overlaps 0 / gaps 0 / audio_collisions 0 / source_overruns 0

## Brief output

`timelines/pass-15-captions-travel-chronology-ai-brief.yaml` is 265
lines vs 2,423 in the full dump (**9.1× compression**, well above the
5× target). The brief frontloads:

- 10 story beats, each with allowed_phases vs observed_phases, member
  clip_ids, and coverage seconds. All 10 beats have observed_phases ⊆
  allowed_phases (no chronology mix surprises in the brief view).
- 8 voiceover windows + 10 music windows, sorted by start, with file
  basenames.
- 73 compact `[start, end, clip_id, lane]` rows for active_visual.

Net: an agent reading just the brief has enough to plan an
`edit_patch_plan.json` for almost any normal request.

## Semantic validator output

`timelines/pass-15-captions-travel-chronology-semantic-issues.yaml`:

| Code | Count |
| --- | --- |
| `MISSING_TIMELINE_START_ERROR` | 73 |
| `CHRONOLOGY_ERROR` | 0 |
| `VO_CUTOFF_ERROR` | 0 |
| `DIALOGUE_COLLISION_WARNING` | 0 |
| `STILL_UNDER_VO_WARNING` | 0 |
| `PACING_WARNING` | 0 |

### What this means

- **73 enabled clips with NULL timelineStart** — out of 91 enabled
  clips, 80% rely on the cursor-resolved positions from
  `dump_timeline.py`'s `resolve_timeline_starts`. This is the
  documented deferred work. Item 13's
  `fill_explicit_timeline_starts.py` is the targeted fix; item 14
  flips the validator from "tolerate cursor fallback" to "hard error
  on any null".
- **Zero chronology errors** — `STORY_BEATS.yaml` correctly describes
  Pass 15. Every active-visual segment's source story_phase is allowed
  in the beat it lands in. The cross-check in item 2 already
  confirmed this; the validator confirms it via the live dump too.
- **Zero VO cutoffs** — every voiceover has at least
  `vo_duration + 0.4s` of visual coverage. The auto-extend safety
  added in v10's `finish_montage_with_vo_and_music` is doing its job.
- **Zero dialogue collisions** — three first-pass false positives on
  the `ambient`-lane b-roll under VO_01 chunks were correctly
  re-classified after the validator was made lane-aware: only `a_roll`
  segments play their source audio at render time. The other lanes
  (`ambient`, `b_roll`, `still`) are silent-cover by convention.
- **Zero still-under-VO warnings** — no still sits in the active
  visual lane for more than 6s under any VO. The longest stills are
  the `still` lane cutaways at 5s (e.g. snack-still under VO_02).
- **Zero pacing warnings** — every VO is either short enough to ride
  on a single visual or already broken by an a-roll burst / title
  card / multi-segment cover.

## Synthetic test results

To prove the warnings actually fire (Pass 15 doesn't trip them):

- `PACING_WARNING`: synthetic 25s VO with single b-roll cover → fires.
- `STILL_UNDER_VO_WARNING`: synthetic 8s still under VO → fires.
- `VO_CUTOFF_ERROR`: synthetic 10s VO with 5s of cover → fires with
  "visual coverage 5.00s < required 10.40s".

## What's not yet checked

The validator deliberately does NOT (yet) verify:

- Audio levels at render time (loudness consistency across cuts).
- VO seam noise on the chunked VO_01 splits.
- Render-vs-yaml drift (item 16's `compare_render_to_timeline.py` will).
- Whether AI-generated patches actually end up matching the rendered
  mp4 (item 17 runs both renderers in parallel).

## Action items

1. **Item 13** — write `fill_explicit_timeline_starts.py` and clear
   the 73 MISSING_TIMELINE_START_ERROR. The `active_visual` after
   that script runs must be byte-identical to the current dump.
2. **Item 14** — promote the validator's "hardware error on any null"
   posture once Item 13 has cleared the baseline.
3. **Item 9 → 12** — patch-based editing layer so future passes touch
   SQLite via typed operations rather than ad-hoc SQL.

This baseline is what Week 2+ work measures against. Any new pass that
*adds* errors or warnings is a regression and must be explained in its
pass log.
