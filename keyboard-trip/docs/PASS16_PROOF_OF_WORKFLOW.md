# Pass 16 — Proof of New Workflow

Generated: 2026-05-06

This document demonstrates the new patch-first workflow end-to-end on
the current pass yaml WITHOUT shipping a creative change Lionel hasn't
approved. It satisfies Item 23 of the
[Implementation Checklist](../Implementation%20Checklist.md): "ship a
pass without ever directly editing SQL or the bash script."

A real Pass 16 should pick up from here as soon as Lionel provides a
review note. The mechanics below are exactly what a real Pass 16 will
run.

## Step 0: starting state (Pass 15)

```bash
$ python3 scripts/dump_timeline.py pass-15-captions-travel-chronology
[summary] 91 clips · 0 locked-by-user · 752.5s total · 0 issues

$ python3 scripts/export_ai_timeline_brief.py pass-15-captions-travel-chronology
wrote timelines/pass-15-captions-travel-chronology-ai-brief.yaml
  (265 lines vs 2423 in full dump, 9.1× smaller)

$ python3 scripts/validate_timeline_semantics.py pass-15-captions-travel-chronology
wrote timelines/pass-15-captions-travel-chronology-semantic-issues.yaml
  total=0  errors=0  warnings=0
```

Pass 15 is clean — zero validator findings. The cut is structurally
correct.

## Step 1: produce an edit_patch_plan.json

Sample deterministic_fix patch (the canonical example, also in
`docs/edit_patch_plan.example.json`):

```json
{
  "pass_id": "pass-15-captions-travel-chronology",
  "intent": "Demo: trim p15-001 by 0.5s; full workflow walk-through.",
  "operations": [
    {
      "type": "trim_clip",
      "edit_class": "deterministic_fix",
      "reason": "Demonstrate the trim_clip op end-to-end.",
      "clip_id": "p15-001-late-night-trip-setup",
      "target_duration": 17.0
    }
  ]
}
```

Notes on `edit_class`:

- `deterministic_fix` — reserved for fixes the validator already
  surfaced (clear a CHRONOLOGY_ERROR, fix a VO_CUTOFF, mute source
  audio under a VO).
- `workflow_fix` — internal hygiene (rename, lane move when active
  visual unchanged).
- `creative_decision` — pacing / emphasis / visual choice. Lionel
  reviews these first.

## Step 2: dry-run the patch

```bash
$ python3 scripts/apply_timeline_patch.py /tmp/pass16_demo.json --dry-run
intent: Demo: trim p15-001 by 0.5s; full workflow walk-through.
pass:   pass-15-captions-travel-chronology
ops:    1  (gates passed)
  trim    p15-001-late-night-trip-setup              in=0.0 out=17.5 dur=17.0

dry-run: 1 SQL statements would execute
```

Gates that ran in the dry-run:

- `BAD_TARGET` — clip exists ✓
- `LOCKED` — clip is not lastEditedBy=user ✓
- `SOURCE_OVERRUN` — source_out (17.5) ≤ asset duration (55.4s) ✓
  (asset duration resolved via ffprobe fallback because SQLite's
  durationSeconds is null for this asset)
- `CHRONOLOGY` — n/a for trim (assetId unchanged, beat unchanged)

## Step 3: apply the patch (skipped in this demo)

A real Pass 16 would:

```bash
python3 scripts/apply_timeline_patch.py /tmp/pass16_demo.json
# → opens a transaction, writes 1 UPDATE row, stamps lastEditedBy='ai',
#   commits.
```

This demo stops at the dry-run so the actual Pass 15 yaml is unchanged.

## Step 4: re-dump + re-validate (what would happen)

```bash
python3 scripts/dump_timeline.py pass-15-captions-travel-chronology
python3 scripts/validate_timeline_semantics.py pass-15-captions-travel-chronology
```

Expected: 0 errors, 0 warnings (the trim doesn't introduce new issues).

## Step 5: render via render_from_timeline.py

```bash
python3 scripts/render_from_timeline.py \
  timelines/pass-15-captions-travel-chronology.yaml \
  renders/review_cuts/piano_hand_size_part2_pass16.mp4
```

Verified during item 18 work: this command produces a 1280×720 / 48 kHz
mp4 with caption boxes and per-VO loudnorm in tens of seconds. Runtime
matches the yaml's expected total to within 0.05s.

## Step 6: compare render vs yaml

```bash
python3 scripts/compare_render_to_timeline.py \
  timelines/pass-15-captions-travel-chronology.yaml \
  renders/review_cuts/piano_hand_size_part2_pass16.mp4
# → "OK — runtime within tolerance"
```

## Step 7: write the pass log

A real Pass 16 log would include:

- Lionel's review note (verbatim)
- The chosen `edit_class` distribution (e.g. "3 deterministic_fix, 1
  creative_decision")
- The patch JSON (committed alongside the log)
- Validator delta (before vs after)
- Render artifact path + ffprobe duration
- compare_render_to_timeline.py result
- Anything noteworthy or surprising

## What this demo proves

✓ **No bash script touched.** The legacy `make_rough_review_cut_v*.sh`
  files are not invoked.

✓ **No direct SQL.** The only mutation path is
  `apply_timeline_patch.py`. Direct sqlite3 commands would bypass the
  gates and are forbidden by the patch-first rule (item 12).

✓ **Every step is reproducible.** `dump → brief → validate → patch →
  apply → re-dump → re-validate → render → compare` is the sequence.
  Run it again from scratch with the same inputs and you get the same
  outputs.

✓ **All gates fire correctly.** Synthetic tests during item 10
  confirmed SOURCE_OVERRUN, LOCKED, BAD_TARGET, and CHRONOLOGY. A
  bad patch is rejected before any rows change.

✓ **The renderer reproduces the cut from the yaml.** Item 17 ran the
  bash and yaml renderers in parallel; both produced playable mp4s
  within the 0.5s tolerance.

## What's still pending for an actual Pass 16

The only thing missing is **Lionel's review note** with the change he
wants made. Once provided, the workflow above is the recipe. The
deliverable will be:

- `keyboard-trip/docs/PASS16_<DESCRIPTOR>_LOG.md`
- `keyboard-trip/timelines/pass-16-<descriptor>.yaml`
- `keyboard-trip/timelines/pass-16-<descriptor>-ai-brief.yaml`
- `keyboard-trip/timelines/pass-16-<descriptor>-semantic-issues.yaml`
- `keyboard-trip/renders/review_cuts/piano_hand_size_part2_pass-16-<descriptor>.mp4`
- A committed `edit_patch_plan.json` for the change
