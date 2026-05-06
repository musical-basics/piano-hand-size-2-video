# Implementation Checklist

Derived from [Implementation Plan.md](Implementation%20Plan.md). Items
ordered by the plan's "Recommended implementation order" (Phase 9), so
work through Week 1 → Week 4 top to bottom.

Each item has:
- The plan step number it implements
- Concrete acceptance criteria (what "done" means)
- Files to create/modify

Start at the top of Week 1 and tick off as you go.

---

## Week 1 — Deterministic infrastructure

### [x] 1. Add ASSET_INTELLIGENCE.yaml (Plan Step 5 + 6)

- Create `keyboard-trip/docs/ASSET_INTELLIGENCE.yaml`
- One entry per source asset listed in `docs/ASSET_INDEX.md`
- Required fields per asset: `asset_id`, `file`, `trip_order`,
  `story_phase`, `clip_type`, `has_dialogue`, `has_motion`,
  `visual_summary`, `best_ranges` (with `in`/`out`/`reason`),
  `avoid_ranges`
- Use the recommended `story_phase` values: `intro`, `trip_setup`,
  `drive_to_titusville`, `factory_visit`,
  `technical_keyboard_stills`, `post_pickup_argument`,
  `car_trouble_return`, `home_demo_payoff`, `pickup_to_record`
- Use the recommended `clip_type` values: `talking_head`,
  `driving_broll`, `gas_station`, `food_stop`, `factory_broll`,
  `keyboard_demo`, `keyboard_still`, `lake_broll`, `car_trouble`,
  `home_demo`, `title_card`, `placeholder`, `music`, `voiceover`
- For `visual_summary` and `best_ranges`, use the existing contact
  sheets in `footage/91_Visual_Contact_Sheets/` plus the transcripts
  in `footage/<bin>/*.txt`

**Done when**: every clip in `ASSET_INDEX.md` has an entry; `yq` /
PyYAML can parse the file.

### [ ] 2. Add STORY_BEATS.yaml (Plan Step 8)

- Create `keyboard-trip/docs/STORY_BEATS.yaml`
- Define beats covering the full master timeline of the current pass
- Each beat: `id`, `start`, `end`, `purpose`,
  `allowed_story_phases` (subset of the values from Step 1)
- Beats based on the current Pass 15 active_visual structure
- Match the narrative spine in `docs/VIDEO_PLAN.md`

**Done when**: beats span 0s → cut runtime with no gaps; every beat
references valid story_phase values.

### [ ] 3. Build export_ai_timeline_brief.py (Plan Step 7)

- Create `keyboard-trip/scripts/export_ai_timeline_brief.py`
- Reads the current pass yaml from
  `keyboard-trip/timelines/<pass-id>.yaml`
- Outputs `keyboard-trip/timelines/<pass-id>-ai-brief.yaml`
- Brief contains: `pass_id`, `runtime`, `issues_summary`,
  `locked_clips`, `story_beats` (with which clips fall in each),
  `active_visual`, `audio_windows`, `problem_flags`
- Compact — should be <5x smaller than the full dump
- AI agents read this BEFORE the full dump

**Done when**: `python3 scripts/export_ai_timeline_brief.py
pass-15-captions-travel-chronology` writes a brief yaml; manual
inspection shows it's actionable on its own.

### [ ] 4. Build validate_timeline_semantics.py (Plan Steps 9–13)

- Create `keyboard-trip/scripts/validate_timeline_semantics.py`
- Reads the current pass yaml + ASSET_INTELLIGENCE.yaml + STORY_BEATS.yaml
- Implements 5 checks:
  - **Chronology**: active visual's `story_phase` must be in the
    current beat's `allowed_story_phases`. Errors as `CHRONOLOGY_ERROR`.
  - **Still-under-VO**: warn if a still is the active visual under a
    voiceover for >6 seconds. Tag as `STILL_UNDER_VO_WARNING`.
  - **VO cutoff**: visual coverage under each VO must be ≥
    `vo_duration + 0.4s`. Tag as `VO_CUTOFF_ERROR`.
  - **Dialogue collision**: when a VO is active and the underlying
    a-roll has `has_dialogue: true`, warn unless source audio is
    explicitly muted/ducked. Tag as `DIALOGUE_COLLISION_WARNING`.
  - **Missing explicit timelineStart**: every enabled clip must have
    a non-null `timelineStart`. Tag as `MISSING_TIMELINE_START_ERROR`.
- Output: prints summary + writes
  `keyboard-trip/timelines/<pass-id>-semantic-issues.yaml`
- Exits non-zero if any errors (warnings are OK)

**Done when**: runs cleanly against the current pass; emits at least
one warning that matches reality (e.g. the VO_01 chunk seam noise we
already know about).

### [ ] 5. Add Long-VO validator (Plan Step 13)

Add to the same `validate_timeline_semantics.py`:
- Rule: no continuous VO+b-roll block >15-20s without one of:
  A-roll burst, natural sound moment, title card, major visual change.
- Tag as `PACING_WARNING`.

**Done when**: validator catches a synthetic case (e.g. an
artificially long single VO clip with no breaks).

### [ ] 6. Update AGENT_HANDOFF.md and INSTRUCTIONS.md with new pass checklist (Plan Step 1)

- Add a "Required pre-pass sequence" to both:
  1. dump current timeline
  2. read AI timeline brief
  3. read active_visual
  4. read issues + semantic warnings
  5. identify user-locked clips
  6. produce `edit_patch_plan.json` (see Step 8 below)
  7. dry-run the patch (Step 10 below)
  8. apply the patch
  9. re-dump
  10. compare before/after
  11. write pass log with the diff

**Done when**: both docs reflect the new ordered checklist; old
"snapshot first / respect locks / use contact sheets / validate /
read VIDEO_PLAN" 5-rule list still exists but is wrapped by this
fuller sequence.

### [ ] 7. Add Division-of-Labor section to AGENT_HANDOFF.md (Plan Step from Phase 8)

Append to AGENT_HANDOFF.md:
- Deterministic code owns: timeline starts/durations, source overrun
  checks, chronology rules, render duration, VO cutoff prevention,
  user lock protection, dialogue collision detection, render-from-yaml
- AI agent owns: emotional visual choices, pacing intuition, narration
  splits, choosing among validated candidate b-roll, title cards, pass
  logs
- AI agent must never: edit script + DB by hand as separate truths,
  overwrite user-locked clips, insert clips without explicit
  timelineStart, ignore validation warnings, use out-of-chronology
  footage without an explicit `flash_forward` flag

**Done when**: section is in AGENT_HANDOFF.md.

### [ ] 8. Run the full Week-1 stack against current pass

- `dump_timeline.py <current-pass>` to refresh
- `export_ai_timeline_brief.py <current-pass>` writes the brief
- `validate_timeline_semantics.py <current-pass>` runs and reports
- Document findings in a one-shot `WEEK1_BASELINE_REPORT.md` so we
  know what the validators surfaced on real data

**Done when**: report exists; current pass is still renderable; we
have a baseline of warnings/errors to fix in subsequent passes.

---

## Week 2 — Patch-based editing (deterministic application)

### [ ] 9. Define the edit_patch_plan.json schema (Plan Step 2)

- Document the schema in
  `keyboard-trip/docs/EDIT_PATCH_PLAN_SCHEMA.md`
- Required top-level fields: `pass_id`, `intent`, `operations[]`
- Each operation has a `type` (one of: `insert_clip`, `disable_clip`,
  `move_clip`, `trim_clip`, `replace_visual`, `split_clip`,
  `set_volume`, `mute_source_audio`, `duck_music`)
- Each operation has a `reason` (required) and an `edit_class`
  (one of: `deterministic_fix`, `workflow_fix`,
  `creative_decision` — see Plan Step 4)
- Provide a JSON Schema file
  (`keyboard-trip/docs/edit_patch_plan.schema.json`) for validation

**Done when**: schema doc explains every field; jsonschema validator
can validate a sample patch.

### [ ] 10. Build apply_timeline_patch.py (Plan Step 24)

- Create `keyboard-trip/scripts/apply_timeline_patch.py`
- Reads `edit_patch_plan.json`
- For each operation, applies the corresponding SQLite change
- Stamps `lastEditedBy = 'ai'` and current timestamp on every row
  it touches
- Supports a `--dry-run` flag (Plan Step 26)
- Validates BEFORE applying (Plan Step 25):
  - sourceOut ≤ asset duration
  - target clip exists (for ops that need it)
  - new clip doesn't create disallowed overlaps
  - clip's story_phase allowed by the beat it lands in
  - no attempt to modify any `lastEditedBy: user` clip
  - no enabled clip ends without an explicit `timelineStart`
- Errors are returned with the offending op's index and a clear message

**Done when**: a sample patch with one of each op type applies cleanly
in dry-run mode; an intentionally-bad patch (overrun, locked clip) is
rejected with the right error.

### [ ] 11. Add GUI semantic-warning display (Plan Step 20)

In `ai-agent-video-editor`:
- Add visual indicators on clip blocks in `timeline-panel.tsx`:
  - red underline = hard validation error
  - yellow underline = semantic warning
  - lock icon = `lastEditedBy: user`
  - clock icon = chronology issue
  - speaker icon = dialogue collision
  - image icon = still under VO
- Source the warnings from the latest semantic-issues yaml (so the
  GUI matches what the validator saw)

**Done when**: open the editor, current-pass clips show appropriate
icons; tooltip explains each warning.

### [ ] 12. Make patch-first editing the new requirement

- Update INSTRUCTIONS.md and AGENT_HANDOFF.md so direct SQL is
  forbidden (or at least documented as last-resort, with a justification
  comment in the pass log)
- All AI passes from now on must use `apply_timeline_patch.py`
- Document the transition: pre-Pass-N passes used direct SQL,
  Pass-N+ uses patches

**Done when**: docs reflect the new rule.

---

## Week 3 — Source-of-truth fixes

### [ ] 13. Build fill_explicit_timeline_starts.py (Plan Step 19)

- Create `keyboard-trip/scripts/fill_explicit_timeline_starts.py`
- Loads the current pass
- Resolves clip starts using current cursor/order logic (mirror
  `dump_timeline.py`'s `resolve_timeline_starts`)
- Writes explicit `timelineStart` to every enabled clip whose
  current `timelineStart` is null
- Re-dumps and confirms `active_visual` is byte-identical

**Done when**: running the script + a re-dump produces the same
`active_visual` as before; subsequent dumps show zero null
`timelineStart` values.

### [ ] 14. Deprecate the order cursor system (Plan Step 18)

- Add a validator that flags any enabled clip with null
  `timelineStart` as a hard error (extend
  `validate_timeline_semantics.py`)
- Update INSTRUCTIONS.md: "Every enabled timeline_item must have an
  explicit `timelineStart`. The order column is now only for stable
  sorting on UI tie-breaks, not for inferring positions."
- The dump script's cursor logic stays as a fallback for legacy data
  but is no longer the primary path

**Done when**: validator errors on any null `timelineStart`; current
pass passes after running Step 13's migration.

### [ ] 15. Build minimal render_from_timeline.py (Plan Step 15)

- Create `keyboard-trip/scripts/render_from_timeline.py`
- First version supports: video clips, still clips, title cards,
  voiceover audio, music beds, rotation, sourceIn/sourceOut,
  timelineStart, duration, basic volume, basic fade
- Reuses the existing helper functions' ffmpeg flag patterns
- Usage:
  `python3 scripts/render_from_timeline.py <pass-yaml> <output-mp4>`

**Done when**: produces an mp4 from the current pass yaml that plays;
duration within ±0.5s of the bash-rendered version.

### [ ] 16. Add compare_render_to_timeline.py (Plan Step 17)

- Create `keyboard-trip/scripts/compare_render_to_timeline.py`
- Inputs: yaml + mp4
- Checks:
  - expected runtime from yaml vs actual runtime from ffprobe
  - expected number of visual segments vs actual
  - expected audio window count vs actual
- Errors if duration differs by >0.5s

**Done when**: passes for the current bash-rendered mp4 vs current
pass yaml; correctly errors when run against a deliberately-stale yaml.

### [ ] 17. Run both renderers in parallel for one pass (Plan Step 16)

- Pick the next pass (Pass 16+) and render it BOTH ways:
  bash + render_from_timeline.py
- Compare:
  - runtime
  - clip count
  - active visual windows (using dumped active_visual)
  - audio windows
- Document any mismatches in the pass log

**Done when**: parallel render works; mismatches are noted and either
fixed or accepted with explanation.

---

## Week 4 — Cut over and improve

### [ ] 18. Expand render_from_timeline.py to feature parity (Plan Step 15 cont.)

- Add support for: captions (drawtext lower-third boxes), montage
  fade-in/out, audio loudnorm, music ducking, multi-audio mix
- All v10/v11/v12 helpers should be representable as patches the
  YAML renderer understands

**Done when**: render_from_timeline.py reproduces the latest bash
script's output to within visual/audio tolerance.

### [ ] 19. Stop editing bash scripts manually

- Make a decision: bash scripts are now archival, not editable
- All future passes go: edit yaml → render_from_timeline.py → mp4
- Update AGENT_HANDOFF.md to reflect

**Done when**: at least one pass is shipped via yaml→render only,
with no bash script changes.

### [ ] 20. Build find_candidate_broll.py (Plan Step 21)

- Create `keyboard-trip/scripts/find_candidate_broll.py`
- Args: `--story-phase`, `--clip-type`, `--min-duration`,
  `--exclude-used` (defaults to true)
- Reads ASSET_INTELLIGENCE.yaml's `best_ranges` for matching assets
- Cross-references current pass's used clips/ranges to exclude
  already-used material
- Outputs ranked candidates with `asset`, `range`, `score`, `reason`

**Done when**: returns useful results for at least 3 sample queries;
matches what a human editor would suggest.

### [ ] 21. Add make_fine_contact_sheet.sh (Plan Step 22)

- Create `keyboard-trip/scripts/make_fine_contact_sheet.sh
  <asset> <start> <end>`
- Generates a 0.5s-resolution contact sheet for the given range
- Output to a separate folder so it doesn't clutter the global
  contact sheets

**Done when**: invoking it on a known clip produces a denser sheet;
visually inspectable in Finder.

### [ ] 22. Add word-level transcripts for talking-head clips (Plan Step 23)

- Modify `scripts/transcribe_all.py` to write word-level timestamps
  in addition to segment timestamps
- Output format: each `.txt` file gets a sibling `.json` with
  `transcript_segments[]` (each with `text`, `start`, `end`)
- Re-transcribe all talking-head clips
- Update the cut-script helpers (or render_from_timeline.py) to use
  these for natural sentence-end cut points instead of the flat +1.5s
  buffer

**Done when**: every talking-head .MOV has a sibling .json with
word-level timing; future passes can cut at sentence boundaries
deterministically.

---

## Cross-cutting acceptance

### [ ] 23. Pass 16+ proves the new workflow

After all the above:
- Pick a real review note from Lionel
- Produce an `edit_patch_plan.json` with the right `edit_class` tags
- Dry-run, apply, render via render_from_timeline.py
- Validate semantics (no new warnings/errors)
- Compare render to timeline (passes)
- Write pass log with before/after diff

**Done when**: we ship a pass without ever directly editing SQL or
the bash script.

---

## Notes for the implementer

- Stay strict about the "no creative edits during this work" rule
  from the plan's agent prompt. The deliverable is the system, not a
  better Pass 16.
- Each item commits and pushes when complete. Don't batch.
- Surface unresolved design questions in the pass log of the relevant
  step rather than guessing.
- If a step's acceptance criterion can't be met because of a
  pre-existing bug, file it in `KNOWN_ISSUES.md` and move on.
