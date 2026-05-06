# Workflow for External Review

This document is written for an external AI (or human) reviewer who's
been handed this project and asked to assess the workflow. It is
deliberately reflective rather than operational — for the operational
playbook, read [AGENT_HANDOFF.md](AGENT_HANDOFF.md).

## TL;DR

We're rough-cutting a 12-minute YouTube vlog with a hybrid setup:
- A **shell-script renderer** (`make_rough_review_cut_v<N>.sh`) that
  composes ffmpeg calls into the actual mp4
- A **Next.js editor app** that reads/writes a SQLite database
  representing the timeline, with drag/trim/slip/marquee/context-menu
  interactions
- A **per-pass yaml snapshot** (`timelines/<pass-id>.yaml`) generated
  from SQLite, that serves as the single source of truth the AI must
  read before any edit
- An **edit-author tracking** column (`lastEditedBy`) so manual UI
  edits are protected from being overwritten by AI passes
- **AI-generated voiceovers** (Cartesia clone of Lionel's voice) and
  **AI-generated music beds** (Replicate Stable Audio 2.5)

## What we're trying to solve

The original problem: AI editing passes were silently overwriting
manual adjustments. The pass-to-pass workflow was:

1. Lionel watches the latest cut, gives notes
2. AI edits the next pass's shell script and renders
3. (somewhere in here, Lionel maybe hand-tweaks something in Final Cut)
4. AI does another pass — but works from the *script*, not from the
   live edit state, so any manual tweak is gone

The deeper issue: **the source of truth was ambiguous**. There was the
shell script, the seed data in the editor app's `db.ts`, the live
SQLite, and Lionel's mental model. Four sources, no synchronization.

## What we built

### One file per pass = the canonical state

Every pass dumps a yaml file that captures the full timeline state at
that point. Three sections:

```yaml
clips:                    # one entry per timeline_item
  - id: p13-vo01a-broll-rainy
    section: VO 01a Late-Night Thesis
    track: ambient
    is_top_visual: true
    timeline: { start: 51.5, end: 56.5, duration: 5.0 }
    source:
      file: footage/02_Drive_To_Titusville/010_IMG_0266_drive_broll_2.MOV
      in: 0
      out: 5
      asset_duration: 33.17
    rotation: 0
    last_edited_by: ai
    last_edited_at: 2026-05-04T05:36:48Z
    contact_sheet: { path: footage/91_Visual_Contact_Sheets/010_IMG_0266_drive_broll_2/, sheets: 1, status: ok }
    notes: "Pass 13: rainy drive under VO_01a thesis."

active_visual:            # derived view: linear "what's on top"
  - window: [0.0, 7.5]
    clip_id: p13-005-front-facing-intro-open
    lane: a_roll
  - ...

issues:                   # validation results
  overlaps: []
  gaps: []
  audio_collisions: []
  source_overruns: []
```

The yaml is the contract. It diffs cleanly in git (one file per pass
in `timelines/`), it's readable by AI and humans, and the validation
section is the regression alarm.

### Pre-pass contract

Five rules an AI editing pass must follow, encoded in
`docs/INSTRUCTIONS.md` and `docs/AGENT_HANDOFF.md`:

1. **Snapshot first** — run `dump_timeline.py <pass-id>` before any
   edit. The dump is the only authoritative input.
2. **Respect `last_edited_by: user`** — clips manually adjusted in the
   UI are locked. AI may shift adjacent clips around them, never the
   locked clip itself.
3. **Use the contact sheets** — every clip's yaml entry points at a
   2-second-grid JPG folder. AI must read those when picking new
   in/out points.
4. **Validate after** — `issues` count must not regress.
5. **Read the spine** — `VIDEO_PLAN.md` is the narrative north star.

### Edit-author tracking

The SQLite `timeline_items` table has `lastEditedBy` (`'user'` or
`'ai'`) and `lastEditedAt` columns. Every UI mutation (drag, trim,
split, delete, duplicate) stamps `'user'`. Every AI-driven SQL update
stamps `'ai'`. The dump surfaces these per-clip so the next AI pass
knows what's locked.

### Render pipeline

Each pass has its own bash script under `keyboard-trip/scripts/`:

```
make_rough_review_cut_v1.sh ... v10.sh
```

The script is a sequence of ffmpeg calls wrapped in helpers:
`add_video`, `add_still`, `add_card`, `add_card_with_music`,
`start_montage` / `montage_piece_*` / `finish_montage_with_vo_and_music`.
Music routing is per-section (`MUSIC_BED="$MUSIC_LATE_NIGHT"` etc).
VO loudness is normalized at render time
(`loudnorm=I=-16:LRA=11:TP=-1.5`).

### Editor app (Next.js + SQLite)

Local-only React frontend in a separate git repo
(`musical-basics/ai-agent-video-editor`). Talks directly to a SQLite
file via `better-sqlite3` from server actions. Capabilities:

- Drag clip body to move (changes `timelineStart` and optionally
  `role` if dropped on a different lane row)
- Drag clip edges to trim (changes `sourceIn`, `sourceOut`,
  `targetDuration`)
- Hold T to slip-mode (both source in/out shift, position fixed)
- Marquee selection (click+drag empty timeline, modifier keys)
- Right-click context menu (Reveal in Finder via macOS `open -R`,
  Open file, Copy path, Split, Duplicate, Delete)
- Inspector panel with editable number inputs for selected clip
- Audio mixer plays all overlapping VO+music tracks at the playhead,
  deduped by source URL
- Preview pane follows the playhead (not the explicit selection),
  prefers highest-priority visual lane
- Keyboard shortcuts: Space, S (split), ⌘D (dup), Delete, ⌘Z/⌘⇧Z,
  ⌘= / ⌘- / ⌘0 (zoom), T (slip toggle)
- Undo/redo for patch edits (not for split/delete/duplicate)

The editor commits all mutations through server actions in
`src/app/actions.ts`. No REST API; just Next.js server actions over
the same process.

### Voiceovers

`scripts/regenerate_voiceovers.py` re-clones Lionel's voice in
Cartesia (model `sonic-3`) from his real recording for `VO_01`, then
regenerates `VO_02..VO_06` from
`audio/voiceovers/TRAVEL_VO_SCRIPT.md`. Long VOs can be split at
sentence boundaries with ffmpeg `-ss`/`-to`; Pass 13 split VO_01 (40s)
into three sentence chunks.

### Music beds

`scripts/generate_music_bed.py "<prompt>" 60 <basename>` calls
Replicate Stable Audio 2.5. ~$0.05–0.10 per generation, max 190s.
Outputs mp3 (the `output_format` param is ignored by the model).

Notable: prompt phrasing matters a lot. "Ambient cinematic" yields
slow synth drone. "Upbeat indie pop instrumental, plucky acoustic
guitar with light percussion claps and shaker, 110 bpm, optimistic
travel vlog music" yields actual vlog music.

## The per-pass cycle in practice

```
[Lionel watches latest mp4, gives notes]
        ↓
AI: dump_timeline.py <current-pass>     # read live state
AI: read yaml + contact sheets + notes  # plan
        ↓
AI: clone v<N>.sh → v<N+1>.sh           # write the new render
AI: edit v<N+1>.sh surgically           # apply changes
AI: ./v<N+1>.sh → v<N+1>.mp4            # render
        ↓
AI: SQL: insert pass + render rows,     # mirror render in DB
        copy timeline, apply patches    # for editor display
        ↓
AI: dump_timeline.py <new-pass>         # validate
AI: write PASS<M+1>_*_LOG.md            # changelog
AI: commit + push                       # ship
        ↓
[Lionel watches new mp4, repeat]
```

Each cycle takes 15–60 minutes depending on scope. We've shipped
13 passes with this loop.

## What's worked well

- **The yaml-as-truth pattern**. Every disagreement between "what the
  AI thought it did" and "what got rendered" surfaced as a yaml diff.
- **`lastEditedBy` locking**. Lionel manually moved one clip in Pass 8
  to test; the next dump correctly stamped it `user`, the validation
  flagged a new overlap his move created, and subsequent AI passes
  routed around it.
- **Contact sheets as the AI's "eyes"**. We can't show a model 8
  hours of source video, but 320×180 JPG grids of every 2 seconds
  give it enough to pick frames that read well.
- **`finish_montage_with_vo_and_music` self-defending against VO
  cutoffs**. Pass 12 had a 0.28s short montage that truncated "the
  car" off the end of a sentence. Pass 13 added a runtime check that
  extends the silent video to fit the VO if shorter. Bug class
  permanently solved at the helper level instead of in every script.
- **Per-section music routing via global variable**. `MUSIC_BED`
  reassignment before each call avoids touching every helper signature.
- **AI-generated music beds**. Four 60s tracks for ~$0.40 of
  Replicate credit, much better than 15-min procedural drone.

## What's awkward / open questions

These are the parts I'd ask a reviewer to challenge:

1. **Two sources of cut state.** The shell script is the rendered
   truth; the SQLite/yaml is the editor display truth. They drift —
   when I add a clip via SQL the editor shows it correctly but the
   render only includes it if I also added it to the script. We've
   been keeping them in sync manually. Should we generate the script
   *from* the yaml? That would make them one truth but it's a real
   build to write a yaml→ffmpeg renderer that handles all the helper
   semantics (rotation, fades, normalization, music ducking, captions).

2. **Pass-numbering vs script-versioning.** Pass 5 was render v1,
   Pass 6 was v3 (we skipped v2 which was an interim render no one
   reviewed). They're now aligned but the offset is a footgun. Should
   probably collapse to a single sequence.

3. **`order` column in `timeline_items` is awkward.** It's an INTEGER
   that determines cursor-stack order, but we end up assigning values
   like `-10`, `5060`, `1700` to insert clips at specific positions.
   The dump's `_resolved_start` cursor logic has to mirror the
   editor's `getTimelineClips` cursor logic exactly, which is a
   coupling that breaks easily. Should probably enforce explicit
   `timelineStart` for everything.

4. **No render-from-yaml step.** The current loop is "AI edits both
   the script and the SQL by hand, the dump validates after." A
   `render_from_timeline.py` would close the loop — generate the
   script automatically from the yaml, render, re-dump. That would
   eliminate the script-vs-DB drift problem.

5. **Validation is mostly visual.** Audio collision detection treats
   voiceover+music as expected; it doesn't catch a VO accidentally
   stacked over A-roll source dialogue. We've had passes where the mix
   sounded off and validation said "zero issues."

6. **Talking-head buffer is a flat +1.5s.** Some clips overshoot and
   sit on silence at the end. Smarter cut-point detection (silence
   detection in source audio, or word-level Whisper timestamps) would
   land each cut on the actual sentence end.

7. **Captions are burned in at render time** (`drawtext`). Editor
   doesn't show them. If captions become a major feature we need a
   first-class captions table in SQLite + editor UI for them.

8. **MCP / server-based analysis tools** (e.g.
   `mcp-deep-video`) might give better cut-point detection than what
   we have, but it's another moving part. Open question whether the
   improvement justifies the infra.

9. **The editor app and the cut script live in different repos** with
   no shared types. The `TimelineItem` schema is duplicated (Python
   in `dump_timeline.py`, TypeScript in `src/lib/types.ts`). Drift
   waiting to happen.

10. **Contact sheets are 2-second resolution.** For finding the
    *exact* frame to cut on, that's coarse. We'd want 0.5s or
    1s resolution for fine work, which means 4–8x more JPGs.

## What we explicitly chose not to do

- **No FCPXML round-trip yet.** We could export the timeline as
  FCPXML and finish in Final Cut, but for the rough-cut review loop
  that's overkill.
- **No real-time collaboration.** Single user, local-only.
- **No frame-accurate scrubbing.** ffmpeg's video preview in the
  editor is good enough for reviewing pacing; for tight frame-level
  trims, do it in Final Cut.
- **No automatic music selection.** Music is per-section, manually
  chosen by Lionel from the available beds. Could do
  beat-detection + auto-sync but again, overkill for rough cut.
- **No multi-camera angles.** Single-camera vlog.

## Numbers

After 13 passes:

- 10 rough-cut renders (`v1.mp4` through `v10.mp4`), each 11–13 min
- 91 active timeline_items in the current pass
- 0 user-locked clips (the test lock from Pass 8 wasn't carried
  forward; Lionel hasn't manually edited Pass 13 yet)
- 1 procedural music bed retired, 4 AI-generated beds in use
- 6 Cartesia voiceovers, 1 real Lionel voiceover (split into 3
  chunks for VO_01)
- ~$1 of Replicate credit spent total
- ~$5 of Cartesia credit spent total
- Editor app: ~3,500 lines of TypeScript across 3 files
- Renderer: 420 lines of bash (v10)
- Dump tool: 360 lines of Python

## Asked of the reviewer

The kind of feedback we'd find useful:

- **Architectural critique** — is the SQLite + yaml + shell script +
  Next.js setup the right shape? Where's the obvious simplification?
- **What's missing for production-quality cuts?** What separates this
  from a tool a YouTuber would actually pay for?
- **Where's the next AI workflow win?** Smart cut-point detection?
  Auto-pacing? Caption generation? Music-sync to beat?
- **Is the pre-pass contract too strict / too loose?** What's the
  right level of AI autonomy in a content-creative tool?
- **Anything that's clearly a footgun** waiting to bite us?
