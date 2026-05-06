# edit_patch_plan.json — schema

The deterministic input format for `apply_timeline_patch.py` (Plan
Step 2 / Checklist item 9). Every AI pass from Week 2 onward plans its
changes as one of these JSON files BEFORE touching SQLite. The
companion JSON Schema is at
[edit_patch_plan.schema.json](edit_patch_plan.schema.json).

## Top level

```json
{
  "pass_id": "pass-16-broll-rebalance",
  "intent": "Replace the still under VO_05 with motion broll.",
  "operations": [ ... ]
}
```

| field | type | required | meaning |
| --- | --- | --- | --- |
| `pass_id` | string | yes | Target pass id. Must match a row in `passes`. |
| `intent` | string | yes | One-sentence statement of the change's purpose, in plain English. |
| `operations` | array | yes | Ordered list of operations applied in sequence. |

## Operation envelope

Every operation shares the same envelope:

```json
{
  "type": "trim_clip",
  "reason": "VO_05 needs another 2s of cover (semantic VO_CUTOFF_ERROR).",
  "edit_class": "deterministic_fix",
  "...op-specific fields..."
}
```

| field | type | required | meaning |
| --- | --- | --- | --- |
| `type` | enum | yes | One of the operation types listed below. |
| `reason` | string | yes | Why this operation exists. Must be specific (which clip, which problem, which line of script). |
| `edit_class` | enum | yes | One of `deterministic_fix`, `workflow_fix`, `creative_decision`. |

### `edit_class` values

- `deterministic_fix` — fixes a validator error or warning. The "right
  answer" was already known; the AI is just executing it.
  Examples: extending visual cover under a VO to clear `VO_CUTOFF_ERROR`,
  setting an explicit `timelineStart` to clear
  `MISSING_TIMELINE_START_ERROR`, swapping a still that triggered
  `STILL_UNDER_VO_WARNING` for motion b-roll.
- `workflow_fix` — improves how the cut is structured without changing
  what the viewer sees in any meaningful way.
  Examples: renaming a clip id for clarity, regrouping clips by
  section, moving a clip from one lane to another when the active
  visual is unchanged.
- `creative_decision` — a judgment call on pacing, emphasis, or visual
  choice. Lionel reviews these first.
  Examples: splitting a long VO into chunks, swapping the cold-open
  hook line, picking a different b-roll under the main argument.

## Operation types

### `insert_clip`

Adds a new `timeline_items` row.

```json
{
  "type": "insert_clip",
  "edit_class": "creative_decision",
  "reason": "Cover the 25s VO_04 gap with three drive_to_titusville bins instead of one long b-roll.",
  "clip": {
    "id": "p16-vo04-cover-rainy",
    "section": "VO 04 Pennsylvania Road",
    "role": "ambient",
    "asset_id": "asset-010-img-0266-drive-broll-2",
    "timeline_start": 188.0,
    "source_in": 4.0,
    "source_out": 12.0,
    "target_duration": 8.0,
    "rotation_override": null,
    "text_overlay": null,
    "notes": "Pass 16: rainy-road insert under VO_04 to clear PACING_WARNING."
  }
}
```

`clip` fields mirror the SQLite columns. `id`, `section`, `role`,
`asset_id`, `timeline_start`, and one of (`target_duration` OR
`source_in`+`source_out`) are required.

### `disable_clip`

Soft-deletes a clip by setting `enabled=0`. Reversible — keeps the row
for history.

```json
{
  "type": "disable_clip",
  "edit_class": "creative_decision",
  "reason": "The Tesla parking-lot clip distracts from the keyboard story.",
  "clip_id": "p15-016-parking-lot-tesla"
}
```

### `move_clip`

Changes a clip's `timeline_start` and/or `section`.

```json
{
  "type": "move_clip",
  "edit_class": "workflow_fix",
  "reason": "Snap the lake cutaway to the explicit 503.5s start so it stops cursor-stacking.",
  "clip_id": "p15-047-vo05-lake-cutaway",
  "timeline_start": 503.5,
  "section": "VO 05 Lake Pause"
}
```

`section` is optional. `timeline_start` must be set explicitly (no
"after the previous clip" cursor reference).

### `trim_clip`

Adjusts a clip's source range or target duration.

```json
{
  "type": "trim_clip",
  "edit_class": "deterministic_fix",
  "reason": "VO_05 needs +1.5s of cover; extend lake-overlook source_out from 7.0 to 8.5.",
  "clip_id": "p15-048-vo05-lake-overlook",
  "source_in": 0.0,
  "source_out": 8.5,
  "target_duration": 8.5
}
```

Any of `source_in`, `source_out`, `target_duration` may be set. The
validator checks `source_out <= asset_duration`.

### `replace_visual`

Swaps which asset a clip points at, keeping its timeline_start and
duration. Use when you want the same window covered by different
footage.

```json
{
  "type": "replace_visual",
  "edit_class": "deterministic_fix",
  "reason": "Replace IMG_0263.jpg still with motion clip 007 to clear STILL_UNDER_VO_WARNING.",
  "clip_id": "p15-026-vo04-woods-still",
  "asset_id": "asset-007-img-0263-morning-highway-update",
  "source_in": 30.0,
  "source_out": 35.0
}
```

### `split_clip`

Splits one clip into two at a source-relative point. Produces an `_a`
and `_b` row; the original id is replaced.

```json
{
  "type": "split_clip",
  "edit_class": "creative_decision",
  "reason": "Break VO_04 in half so we can insert an a-roll burst at the seam.",
  "clip_id": "p15-024-vo04-pennsylvania-scenery",
  "split_at_source_seconds": 4.0,
  "new_ids": {
    "a": "p16-024a-vo04-scenery-open",
    "b": "p16-024b-vo04-scenery-late"
  }
}
```

### `set_volume`

Adjusts an audio clip's volume in linear gain (0.0–2.0). Affects the
render only; does not modify the source file.

```json
{
  "type": "set_volume",
  "edit_class": "creative_decision",
  "reason": "Lionel says VO_05 sits 1dB too quiet under the lake music.",
  "clip_id": "p15-audio-vo-05-lake-pause",
  "volume": 1.12
}
```

### `mute_source_audio`

Marks a video clip's source audio as muted at render time. The
validator's dialogue-collision check treats this as resolved.

```json
{
  "type": "mute_source_audio",
  "edit_class": "deterministic_fix",
  "reason": "p15-008-pennsylvania-scenery has dialogue that collides with VO_04.",
  "clip_id": "p15-008-pennsylvania-scenery"
}
```

### `duck_music`

Reduces a music bed's volume across a window (typically VO range).

```json
{
  "type": "duck_music",
  "edit_class": "deterministic_fix",
  "reason": "Drop morning_road bed to 0.4 under VO_04 so narration breathes.",
  "clip_id": "p15-audio-music-vo-04",
  "duck_window": [182.5, 200.9],
  "volume": 0.4
}
```

## What the validator checks before apply

`apply_timeline_patch.py` runs these gates BEFORE any SQLite write
(per Plan Step 25):

1. **Source overrun** — every `source_out` must be `<= asset.duration`.
2. **Target existence** — `clip_id` references on `move/trim/replace/
   split/set_volume/mute/duck/disable` must hit a real
   `timeline_items` row in the target pass.
3. **No disallowed overlaps** — `insert_clip` and `move_clip` must not
   create new overlaps that the dump's overlap detector would flag.
4. **Beat chronology** — the resulting clip's source `story_phase`
   (looked up via `ASSET_INTELLIGENCE.yaml`) must be in the beat's
   `allowed_story_phases` (looked up via `STORY_BEATS.yaml`) for the
   window the clip lands in.
5. **No lock violations** — operations targeting clips with
   `lastEditedBy='user'` are rejected unless the patch carries an
   explicit `unlock: true` flag at the operation level (which only
   Lionel should add).
6. **Explicit timelineStart** — every `insert_clip` MUST set
   `timeline_start`. After Item 13 lands, every existing enabled clip
   must already have a non-null timelineStart for the patch to apply.

If any gate fails, the apply is aborted, no rows change, and the
error message names the offending op's index and the failed gate.

## Conventions

- Operations are applied in array order. If a later op depends on an
  earlier op's effect (e.g. trimming a freshly-inserted clip), this is
  fine; the validator runs gates against the post-prior-ops state.
- Use `dry_run` mode (`apply_timeline_patch.py <plan.json> --dry-run`)
  to see the gate report and the would-write summary without touching
  SQLite.
- Patches that contain only `deterministic_fix` ops can be applied
  unattended. `creative_decision` ops should land in a Lionel-review
  loop.
