# Agent Handoff — Piano Hand Size Part 2

You are picking up a YouTube vlog edit project. This file is the
authoritative briefing. Read it before doing anything else.

## What this project is

A 12-minute story-driven YouTube video. Lionel drove overnight from
Baltimore to Titusville, PA to pick up two alternate-sized piano
keyboards (DS 6.0 and DS 5.5) made by David Steinbuhler. The edit is
part vlog, part argument: the trip provides motion, the
hand-size-matters thesis provides meaning. Target tone: Mr Beast vlog
energy with substance.

Source of truth for the edit's intended structure:
[VIDEO_PLAN.md](VIDEO_PLAN.md).

## Repo layout

This working directory holds two independently-versioned repos:

```
Piano Hand Size Part 2/
├── keyboard-trip/             ← THIS REPO (musical-basics/piano-hand-size-2-video)
│   ├── footage/               ← all source clips, organized chronologically
│   ├── audio/
│   │   ├── voiceovers/        ← Cartesia TTS + Lionel's real VO_01
│   │   └── music/             ← AI-generated section-specific beds
│   ├── renders/review_cuts/   ← rough cut mp4s (v1 → v10)
│   ├── scripts/               ← cut scripts, dump tools, generation tools
│   ├── docs/                  ← plan, instructions, pass logs (this doc)
│   ├── timelines/             ← per-pass yaml snapshots (single source of truth)
│   └── piano hand size 2 video.fcpbundle/   ← Final Cut library (binary, gitignored)
└── ai-agent-video-editor/     ← Separate repo (musical-basics/ai-agent-video-editor)
                                  Local-only Next.js editor UI for the same project
                                  Reads/writes its own SQLite at .cut-notes/cut-notes.sqlite
                                  This repo's .gitignore excludes it
```

`PROJECT_STRUCTURE.md` at the workspace root has more detail on the
two-repo arrangement.

## Source of truth: SQLite + dumped yaml

The editor app's `.cut-notes/cut-notes.sqlite` (under
`ai-agent-video-editor/`) is where the timeline lives. The render
scripts are derived from it — never the other way around.

Read the live state via:

```bash
python3 keyboard-trip/scripts/dump_timeline.py <pass-id> [--list] [--all]
```

This writes `keyboard-trip/timelines/<pass-id>.yaml`, regenerates any
missing or stale contact sheets for source clips referenced in that
pass, and runs collision detection. The yaml has three sections you
will use:

- `clips:` — every clip's id, lane, timeline window, source range,
  rotation, contact-sheet path, and `last_edited_by` ("user" or "ai").
- `active_visual:` — linear list of which clip is the top visual at
  every moment of the cut. Read this first to grok the visual flow.
- `issues:` — overlaps, gaps, audio collisions, source overruns. Must
  not regress pass-over-pass.

## The pre-pass contract — READ THIS BEFORE ANY EDIT

Non-negotiable. The five rules of "don't break the cut" still apply
(snapshot first, respect locks, use contact sheets, validate after,
read VIDEO_PLAN). Wrapped around them is the **required pre-pass
sequence** that the new patch-based workflow expects every AI agent to
follow, in this order:

1. **Dump current timeline.**
   `python3 keyboard-trip/scripts/dump_timeline.py <current-pass-id>`
   Writes `timelines/<pass-id>.yaml` from SQLite.
2. **Read the AI timeline brief first.**
   `python3 keyboard-trip/scripts/export_ai_timeline_brief.py <current-pass-id>`
   Writes `timelines/<pass-id>-ai-brief.yaml`. This is the compact
   distillation — story_beats with member clips, locked clips,
   audio_windows, issues_summary. Read this BEFORE the full dump.
3. **Read `active_visual` from the full dump.** It linearly lists
   which clip is the top visual at every second of the cut. Fastest
   way to grok the visual flow before planning changes.
4. **Read issues + semantic warnings.**
   `python3 keyboard-trip/scripts/validate_timeline_semantics.py <current-pass-id>`
   Writes `timelines/<pass-id>-semantic-issues.yaml`. Run this every
   pre-pass — chronology errors, VO cutoff errors, dialogue
   collisions, still-under-VO warnings, and missing-timelineStart
   errors all surface here.
5. **Identify user-locked clips.** `last_edited_by: user` (in the dump
   and the brief) means Lionel adjusted that clip in the editor UI.
   You MUST NOT change its `timeline`, `source.range`, `track`, or
   `rotation`. You MAY shift adjacent clips. To unlock, Lionel says
   so explicitly.
6. **Produce an `edit_patch_plan.json`.** From Week 2 onward (see
   `EDIT_PATCH_PLAN_SCHEMA.md` once item 9 lands), every AI pass plans
   its changes as a typed list of operations with `reason` + `edit_class`
   tags before writing anything to SQLite.
7. **Dry-run the patch.**
   `python3 keyboard-trip/scripts/apply_timeline_patch.py <plan.json> --dry-run`
   Validates source overruns, locked-clip protection, story-beat
   chronology, and explicit-timelineStart presence before any rows
   change.
8. **Apply the patch.**
   `python3 keyboard-trip/scripts/apply_timeline_patch.py <plan.json>`
   Stamps `lastEditedBy='ai'` on every row touched.
9. **Re-dump.** Run `dump_timeline.py` again to capture the new state.
10. **Compare before/after.** Diff the two dumps (and re-run the brief
    + semantic validator). Issues count must be non-increasing
    pass-over-pass; new overlaps/gaps/audio collisions are
    regressions.
11. **Write the pass log.** `PASS<M>_V<N>_<NAME>_LOG.md` records the
    intent, the patch plan, the diff, the validator delta, and any
    creative decisions made.

Always anchor narrative direction in [VIDEO_PLAN.md](VIDEO_PLAN.md):
the thesis ("smaller piano keys change the way you experience the
piano") and the trip's structure are the north star, regardless of
what tools you use to mutate the timeline.

## Patch-first editing (mandatory from Pass 16 onward)

Every AI pass from Pass 16 onward MUST mutate SQLite via
`apply_timeline_patch.py` consuming an `edit_patch_plan.json`. Direct
SQL is forbidden by default — use it only as a documented last resort
with an explicit justification in the pass log explaining why a patch
op type was insufficient.

Why:

- The validator gates run BEFORE any row changes (source overrun,
  story-beat chronology, lock protection, no-new-overlap, explicit
  timelineStart). Direct SQL bypasses every gate.
- Every patched row is stamped `lastEditedBy='ai'` automatically, so
  the user-lock distinction stays accurate.
- Patches are reproducible artifacts that live in the pass log and
  can be diff-reviewed.
- Audio ops (mute/duck/volume) consistently land in the row's notes
  field with a `[audio: ...]` prefix that item 18's
  `render_from_timeline.py` will read, instead of being scattered
  through render scripts.

Workflow:

```bash
# 1. Author the patch
$EDITOR /tmp/patch.json   # follow EDIT_PATCH_PLAN_SCHEMA.md

# 2. Dry-run the gates
python3 keyboard-trip/scripts/apply_timeline_patch.py /tmp/patch.json --dry-run

# 3. Apply
python3 keyboard-trip/scripts/apply_timeline_patch.py /tmp/patch.json

# 4. Re-dump + re-validate
python3 keyboard-trip/scripts/dump_timeline.py <pass-id>
python3 keyboard-trip/scripts/validate_timeline_semantics.py <pass-id>

# 5. Compare semantic-issues before/after; commit the patch in the
#    pass log alongside the diff.
```

Pre-Pass-16 history: passes 5 → 15 mutated SQLite via ad-hoc SQL
embedded in pass-log "Mechanics" sections. Those are archival; do not
copy that pattern. A new pass that needs a fresh op type should
extend the patch schema (item 9) and the apply script (item 10), not
revert to direct SQL.

## Division of labor — what's deterministic vs creative

The system is designed so the "what's mechanically correct" parts are
deterministic code and the "what feels right" parts are AI judgment.
Stay on your side of the line.

**Deterministic code owns** (don't redecide these in narration):

- Resolved timeline starts and durations of every enabled clip.
- Source overrun checks (`sourceOut <= asset duration`).
- Chronology rules (clip's `story_phase` must be in the current beat's
  `allowed_story_phases` from `STORY_BEATS.yaml`).
- VO cutoff prevention (visual coverage `>= vo_duration + 0.4s`).
- User-lock protection (`lastEditedBy: user` is read-only to AI).
- Dialogue collision detection (a-roll with `has_dialogue` under a VO
  with no muted/ducked declaration).
- Still-under-VO warning (>6s threshold).
- Render duration vs yaml duration (item 16's
  `compare_render_to_timeline.py`).
- Render-from-yaml mechanics (item 15+18's `render_from_timeline.py`).

**AI agent owns** (the system can't do these for you):

- Emotional and visual choices — which b-roll best lands a VO line,
  when to hold a still vs cut to a face, when a music swap helps.
- Pacing intuition — when a beat feels too long or too dense, when
  the cut wants a breath.
- Narration splits — where to break a long VO into chunks for
  vlog-style alternation.
- Choosing among validated candidate b-roll (item 20's
  `find_candidate_broll.py` produces a ranked list; you pick).
- Title cards and on-screen text wording.
- Pass logs — the human-readable explanation of what changed and why.

**AI agent must never:**

- Edit the bash render script and the SQLite DB by hand as separate
  truths. The yaml dump is the only truth; bash scripts (until item 19
  cuts them over) and SQLite must always agree.
- Overwrite a `lastEditedBy: user` clip without an explicit unlock
  from Lionel.
- Insert clips without an explicit `timelineStart`. The cursor system
  is being deprecated (item 14); new clips need a real position.
- Ignore validator errors. Warnings can be acknowledged in the pass
  log; errors must be fixed or explicitly justified.
- Use out-of-chronology footage without flagging it as an intentional
  flash-forward (and adding it to the relevant beat's
  `allowed_story_phases`).

## The render pipeline

Each pass has its own shell script. Naming convention:

```
make_rough_review_cut_v<N>.sh  →  piano_hand_size_part2_rough_cut_v<N>.mp4
PASS<M>_V<N>_<DESCRIPTION>_LOG.md
```

Pass numbers and version numbers are not 1:1 — early passes shared
versions (Pass 5 was render v1, Pass 6 was v3, etc.). From Pass 9
onward they run together (Pass 10 → v7, Pass 11 → v8, ..., Pass 15 →
v12).

Each script `cd`s to `keyboard-trip/` and uses relative paths from
there. Run them with:

```bash
./keyboard-trip/scripts/make_rough_review_cut_v<N>.sh
```

Helpers inside the scripts you'll use a lot:

- `add_video <path> <start_s> <duration_s> [rotation]` — single video
  segment. Auto fade-out 0.4s on audio (added in v9). Talking-head
  clips should be padded ~1.5s past the natural sentence end.
- `add_video_captioned <path> <start_s> <duration_s> <rotation> <caption>`
  — single video segment with a burned-in lower caption box (added in v12).
- `add_still <path> <duration_s> [rotation]` — single still image.
- `add_card <duration_s> <text>` — title card, no music.
- `add_card_with_music <duration_s> <text>` — title card with the
  current `MUSIC_BED` ducked underneath.
- `start_montage` / `montage_piece_video` / `montage_piece_still` /
  `finish_montage_with_vo_and_music <vo_path> <label> [caption]` — assemble a
  silent visual montage, then mix in a VO + music track. The finish
  helper auto-extends the silent video if the VO is longer
  (added in v10 to fix the cutoff bug — see Pass 13 log). The optional
  caption burns in a lower caption box across the montage (added in v12).

Music routing: set `MUSIC_BED="$MUSIC_LATE_NIGHT"` (or the relevant
constant) before each section. Constants defined at the top of v9+
scripts.

## Voiceovers

VO_01 is **Lionel's real recording** bounced from Logic. VO_02..VO_06
are **Cartesia TTS** of his cloned voice. Whenever Lionel re-records
or wants to update narration, run:

```bash
python3 keyboard-trip/scripts/regenerate_voiceovers.py
```

This re-clones the voice from the current
`audio/voiceovers/VO_01_late_night_drive.wav`, then regenerates
VO_02..VO_06 from `audio/voiceovers/TRAVEL_VO_SCRIPT.md`. Cartesia
model is `sonic-3`. API key in `.env.local`
(`CARTESIA_API_KEY=…`).

Long VOs can be **split at sentence boundaries** for vlog-style
alternation. Pass 13 split VO_01 (40s) into three chunks
(`VO_01a_late_night_thesis.wav`, `VO_01b_pennsylvania_setup.wav`,
`VO_01c_millimeters_payoff.wav`) using ffmpeg `-ss`/`-to` and the
Whisper-confirmed sentence-boundary timestamps. The sentence
timestamps for any VO are in the matching transcript at
`footage/<bin>/*.txt` (or run `python3 scripts/transcribe_all.py`).

VO loudness is normalized at render time via
`loudnorm=I=-16:LRA=11:TP=-1.5` inside `finish_montage_with_vo_*`
helpers (added in v8). Do not pre-normalize source files.

## Music beds

All four music beds are AI-generated via Replicate's Stable Audio 2.5.
Generate via:

```bash
python3 keyboard-trip/scripts/generate_music_bed.py "<prompt>" <duration_s> <basename>
```

API key in `.env.local` (`REPLICATE_API_TOKEN=…`). Max duration 190s,
~$0.05–0.10 per generation. Output is mp3 (the `output_format` param
is ignored by this model). Saved to `audio/music/<basename>.mp3`.

**Prompt note**: Stable Audio interprets "ambient cinematic" as slow
synth drone. For vlog energy, use prompts like
*"upbeat indie pop instrumental, plucky acoustic guitar with light
percussion claps and shaker, 110 bpm, optimistic travel vlog music"*.
The Pass 12 vs Pass 13 prompts are documented in
[PASS12_V9_BUFFERS_CUTAWAYS_LOG.md](PASS12_V9_BUFFERS_CUTAWAYS_LOG.md).

Current beds (all in `audio/music/`):

- `ai_v1_late_night_drive_60s.mp3` — cold open + VO_01 chunks
- `ai_morning_road_60s.mp3` — VO_02, VO_03, VO_04
- `ai_lake_pause_60s.mp3` — VO_05
- `ai_breakdown_return_60s.mp3` — VO_06

## Editor app capabilities

Lionel reviews and edits in the Next.js app at `ai-agent-video-editor/`.
Run with `npm run dev` from that folder (already running on
http://localhost:3001). It supports:

- **Drag clip body** to move (changes `timelineStart`, can change
  `role` if dropped on a different lane row).
- **Drag clip edges** to trim (changes `sourceIn` / `sourceOut` /
  `targetDuration`).
- **Hold T** then drag to slip (both source in/out shift, position
  fixed).
- **Marquee selection** by click+drag on empty timeline space.
  Cmd/Shift+click on clips toggles individual selection.
- **Right-click clip** → context menu with Reveal in Finder, Open
  file, Copy path, Split, Duplicate, Delete.
- **Keyboard shortcuts**: Space (play/pause), S (split at playhead),
  ⌘D (duplicate), Delete (delete), ⌘Z / ⌘⇧Z (undo/redo for patch
  edits — split/delete/duplicate not in undo stack), ⌘= / ⌘- /
  ⌘0 (zoom timeline), T (toggle slip mode), Esc (cancel slip).
- **Inspector panel** for the selected clip with editable
  `timelineStart`, `sourceIn`, `sourceOut`, `targetDuration`, `role`
  inputs. Commits on blur or Enter.
- **Audio mixer** plays all overlapping voiceover/music tracks at the
  playhead simultaneously, deduped by source URL.
- **Preview pane** follows the playhead (not the explicit selection)
  and prefers the highest-priority visual lane (`a_roll > b_roll >
  still > title_card > placeholder > ambient`).

Every UI mutation stamps `lastEditedBy='user'` and `lastEditedAt=now`
on the row. AI edits stamp `'ai'`.

## How to do a new pass — the recipe

```bash
# 1. Read current state.
python3 keyboard-trip/scripts/dump_timeline.py <current-pass-id>
cat keyboard-trip/timelines/<current-pass-id>.yaml | less

# 2. Identify locked clips (clips with last_edited_by: user). Plan around them.

# 3. For any clip you intend to recut, look at its contact sheet:
ls keyboard-trip/footage/91_Visual_Contact_Sheets/<clip_basename>/
# Open the JPGs in Finder/Preview to see what's actually at each 2s of the source.

# 4. Read open notes from SQLite for context:
sqlite3 ai-agent-video-editor/.cut-notes/cut-notes.sqlite \
  "SELECT id, body, timecodeStart, timelineItemId FROM notes
   WHERE projectId='piano-hand-size-part-2' AND status='open'"

# 5. Read VIDEO_PLAN.md and the latest PASS<M>*_LOG.md for spine + recent context.

# 6. Decide changes. Plan them concretely (list specific clips, durations, music).

# 7. Implement:
#    a. Generate any new music: scripts/generate_music_bed.py "<prompt>" 60 <basename>
#    b. Write make_rough_review_cut_v<N+1>.sh (clone the latest, edit surgically)
#    c. ./keyboard-trip/scripts/make_rough_review_cut_v<N+1>.sh

# 8. Update SQLite: insert new pass row, render-job row, copy timeline_items
#    from the previous pass with id rewrite (REPLACE 'p<old>-' → 'p<new>-'),
#    apply patches/inserts/disables. Then update projects.metadata.currentPass /
#    currentPassId / currentRenderJobId. (Look at any recent PASS<M>*_LOG.md
#    Mechanics section for an example SQL set.)

# 9. Re-dump and validate:
python3 keyboard-trip/scripts/dump_timeline.py <new-pass-id> --skip-contact-sheets

# 10. Write keyboard-trip/docs/PASS<M+1>_V<N+1>_<NAME>_LOG.md.

# 11. git add + commit + push (Lionel's standing rule: commit and push after
#     every completed change). Editor app changes commit separately in its
#     own folder.
```

## Naming conventions

- Pass IDs: `pass-<N>-<kebab-name>` (e.g. `pass-13-vo-split-and-buffer`).
- Render job IDs: `render-v<N>-<kebab-name>` (e.g. `render-v10-vo-split`).
- Timeline item IDs: `p<N>-<kebab-name>` (e.g. `p13-vo01a-broll-rainy`).
- Asset IDs: `asset-<descriptor>` (varies; check existing patterns).
- Pass logs: `PASS<N>_V<M>_<UPPER_SNAKE>_LOG.md`.

## What's been done so far (Pass 5 → Pass 13)

Read these in order if you want the full arc:

- [PASS5_V2_FIX_LOG.md](PASS5_V2_FIX_LOG.md) — first rotation/trim fixes
- [PASS5_V3_FIX_LOG.md](PASS5_V3_FIX_LOG.md) — VO + music cleanup pass
- [PASS7_V4_FIX_LOG.md](PASS7_V4_FIX_LOG.md) — clip note fixes
- [PASS8_V5_VO_MUSIC_LOG.md](PASS8_V5_VO_MUSIC_LOG.md) — first time
  with the procedural music drone
- [PASS9_V6_REAL_VO_LOG.md](PASS9_V6_REAL_VO_LOG.md) — Lionel
  recorded real VO_01 in Logic, voice re-cloned in Cartesia
- [PASS10_V7_FLOW_AND_MUSIC_LOG.md](PASS10_V7_FLOW_AND_MUSIC_LOG.md)
  — chronology fix + AI music beds replace the procedural drone
- [PASS11_V8_VLOG_FLOW_LOG.md](PASS11_V8_VLOG_FLOW_LOG.md) — intro
  first, all-video VO_01 montage (no stills under VO), VO loudness
  normalization
- [PASS12_V9_BUFFERS_CUTAWAYS_LOG.md](PASS12_V9_BUFFERS_CUTAWAYS_LOG.md)
  — talking-head sentence-tail buffers, b-roll cutaways inside the
  main argument and home payoff, music regenerated with upbeat
  indie/vlog prompts
- [PASS13_V10_VO_SPLIT_LOG.md](PASS13_V10_VO_SPLIT_LOG.md) — fixed
  the "chocolate milk and sleeping in the car" cutoff (VO_02
  truncation), VO_01 split into 3 sentence chunks with A-roll
  inserts, helper now self-defends against future cutoffs
- [PASS14_V11_TIMELINE_SYNC_MONTAGE_POLISH_LOG.md](PASS14_V11_TIMELINE_SYNC_MONTAGE_POLISH_LOG.md)
  — repaired SQLite/render source-of-truth drift so cutaways and VO_03
  match the render script, and refined the VO montage helper so it only
  holds the last frame when a VO actually needs extension
- [PASS15_V12_CAPTIONS_TRAVEL_CHRONOLOGY_LOG.md](PASS15_V12_CAPTIONS_TRAVEL_CHRONOLOGY_LOG.md)
  — removed the pre-arrival David/workshop reveal from the travel section,
  added starter burned-in captions, and raised/limited the VO music mix

## Known rough edges as of Pass 15

These are the active problems waiting for the next pass to address:

- **`056_PICKUP_hand_key_comparison.MOV` not yet recorded.** Two
  P056 placeholder cards stand in for it (cold open and home payoff).
  Once Lionel records the comparison shot, replace both placeholders
  with real footage.
- **VO_02..VO_06 are still Cartesia TTS.** The seam between Lionel's
  real VO_01 chunks and the cloned VO_02 voice is audible. Either
  re-record those VOs or accept the seam.
- **VO chunk seams in VO_01a/b/c.** Split with `-c copy` at
  non-keyframe positions; small audible artifacts at the cuts. Not
  bad enough to warrant re-encoding yet.
- **Captions are started, not complete.** Pass 15 adds summary/checkpoint
  captions through the travel/lake/breakdown VO sections. It is not yet
  a full word-for-word subtitle pass.
- **A-roll inserts during VO_01 split** carry their original camera
  audio. The editor timeline is now synced around these inserts, but
  final mix still needs a listen for any music/camera-audio handoff
  that feels abrupt.
- **Talking-head buffer is a flat +1.5s.** Some clips overshoot and
  sit on silence at the end. For the final master, listen and trim
  each clip's exact end manually.
- **Stable Audio 2.5 returns mp3 only.** The model ignores
  `output_format=wav`. Files are `audio/music/*.mp3` with the
  appropriate MIME type served by the editor's media route.
- **Validation tracks visual-only metrics.** Audio collision detection
  treats voiceover+music as expected; it doesn't catch VO overlaps
  with talking-head A-roll source audio. If you stack a VO over an
  A-roll without ducking source audio, validation passes but the mix
  sounds bad.

## Useful commands cheatsheet

```bash
# List all passes:
python3 keyboard-trip/scripts/dump_timeline.py --list

# Dump every pass at once (slow if many contact sheets need generation):
python3 keyboard-trip/scripts/dump_timeline.py --all --skip-contact-sheets

# Open the editor app:
cd ai-agent-video-editor && npm run dev    # http://localhost:3000 (or 3001 if 3000 taken)

# If better-sqlite3 throws ABI mismatch on dev start:
cd ai-agent-video-editor && npm rebuild better-sqlite3

# See current SQLite state of any pass directly:
sqlite3 ai-agent-video-editor/.cut-notes/cut-notes.sqlite \
  "SELECT id, role, timelineStart, sourceIn, sourceOut, targetDuration, lastEditedBy
   FROM timeline_items WHERE passId='<pass-id>' AND enabled=1
   ORDER BY \"order\""

# Check render duration:
ffprobe -v error -show_entries format=duration -of csv=p=0 \
  keyboard-trip/renders/review_cuts/piano_hand_size_part2_rough_cut_v<N>.mp4

# Export current pass as a conservative Final Cut Pro XML:
# primary visual storyline only; no connected-gap clips, captions, VO, or music.
# Current raw-source exporter preserves each source file's native frame
# format/timebase instead of forcing all assets to the 30fps project format.
python3 keyboard-trip/scripts/export_fcpxml.py

# Preferred raw-source Final Cut XML for Lionel:
# source MOV/JPG files stay linked, source clips play video-only unless camera
# audio is explicitly requested, MOV camera display matrices are left for FCP
# to apply, explicit timeline rotations are written as XML transforms, and JPG
# timeline items are emitted as <video> elements rather than <asset-clip>.
# That JPG representation fixed the FCP import crashes on the previously
# failing IMG_0258.jpg / IMG_0260.jpg diagnostics.
python3 keyboard-trip/scripts/export_fcpxml.py \
  --output keyboard-trip/exports/fcpxml/piano_hand_size_part2_pass15_v12_raw_native_timeline_rotations.fcpxml

# Actual multilane Final Cut XML for the Cut Notes edit:
# source media stays linked, visual lanes are mapped to FCP connected lanes,
# voiceover/music come through as separate audio clips, and title/caption
# overlays can be exported as native FCP captions/titles.
python3 keyboard-trip/scripts/export_fcpxml.py pass-15-captions-travel-chronology \
  --timeline-mode connected-gap \
  --title-mode native \
  --force-clip-rotation 042_IMG_0298_tionesta_lake_cutaway.MOV=270 \
  --output keyboard-trip/exports/fcpxml/piano_hand_size_part2_pass15_v12_actual_edit_multilane_native_titles.fcpxml

# Round-trip breadcrumb policy:
# the app's live edit format is SQLite, not the dumped YAML. Exported FCPXMLs
# now carry stable Cut Notes breadcrumbs as cutnotes.* metadata where FCPXML
# allows metadata, plus compact note text (`cutnotes:{...}`) on timeline
# elements that do not allow metadata. A future FCPXML importer should prefer
# cutnotes.timelineItemId / cutnotes.assetId from metadata and fall back to the
# note payload when metadata is absent or stripped by Final Cut.

# Rotation lesson from raw-source FCPXML debugging:
# ffprobe/MOV display-matrix metadata is necessary but not sufficient. 019 and
# 042 both report displaymatrix rotation=-90, but 019 is correct with no extra
# XML transform while 042 needs an additional 270-degree timeline rotation.
# Trust existing timeline/editor rotations when present. When a clip has no
# explicit rotation but looks sideways/upside-down in FCP or in the render,
# generate 0/90/180/270 diagnostic probes and visually score them using human
# content cues: faces upright, lake horizons horizontal, keyboards/labels in
# their expected orientation. Known current finding: 042_IMG_0298 is correct
# with 270.

# Variant with original camera audio on source clips, still no VO/music:
python3 keyboard-trip/scripts/export_fcpxml.py --audio-mode camera \
  --output keyboard-trip/exports/fcpxml/piano_hand_size_part2_pass15_v12_primary_camera_audio.fcpxml

# Raw-source diagnostic that still points at the original MOV/JPG files but
# removes source-audio metadata from video assets to avoid FCP XML audio
# preflight crashes.
python3 keyboard-trip/scripts/export_fcpxml.py --strip-source-audio \
  --output keyboard-trip/exports/fcpxml/piano_hand_size_part2_pass15_v12_raw_native_video_only.fcpxml

# Historical FCP rescue exports if raw-source XML regresses:
# 1. One finished movie as a single FCP clip.
python3 keyboard-trip/scripts/export_fcpxml.py --timeline-mode rendered
# 2. A cuttable timeline made from normalized 720p30 render segments.
#    The segment MP4s live in exports/fcpxml/intermediates/pass15_v12_segments/
#    and are gitignored because they are media files.
python3 keyboard-trip/scripts/export_fcpxml.py --timeline-mode segments
# 3. Best current FCP rescue: one normalized 720p30 MP4 per visual cut,
#    with the final reviewed audio slice baked into each clip. This preserves
#    clip separation without pointing FCP at the crashy raw phone media.
python3 keyboard-trip/scripts/export_fcpxml.py --timeline-mode normalized-clips

# Verify VO loudness on a section of a render:
ffmpeg -y -hide_banner -i <render.mp4> -ss <start_s> -t 20 -vn \
  -af "loudnorm=print_format=summary" -f null -
```

## Standing instructions from Lionel

- Commit and push after every completed change. Don't ask first.
- Don't bypass pre-commit hooks (`--no-verify`). Don't skip signing.
- Never destructive git ops without confirmation (force-push, hard
  reset, branch deletion, amending pushed commits).
- `main` is the deploy branch on most of his projects. This repo
  doesn't deploy but the rule still applies: don't avoid `main`.
- Be terse. He reads the diff. He doesn't want trailing summaries.
