# Project Structure

This working directory holds two independently versioned projects that
collaborate to produce one YouTube video.

```
Piano Hand Size Part 2/
├── keyboard-trip/             ← the video project (this repo)
└── ai-agent-video-editor/     ← the review/notes app (separate repo)
```

## The two repos

| Folder | Remote | Tracks |
| --- | --- | --- |
| `keyboard-trip/` (outer repo) | `musical-basics/piano-hand-size-2-video` | All footage, docs, scripts, audio, renders for the video |
| `ai-agent-video-editor/` | `musical-basics/ai-agent-video-editor` | The Next.js review app source code |

The outer repo's `.gitignore` excludes `ai-agent-video-editor/`, so each
repo is committed and pushed from inside its own folder. The editor app
is intentionally reusable across future video projects, so its history
should not be entangled with this one.

## keyboard-trip/ layout

```
keyboard-trip/
├── footage/         Source clips, stills, contact sheets
│   ├── 01_Trip_Setup … 08_Pickups_To_Record
│   ├── 90_Reference_Frames
│   └── 91_Visual_Contact_Sheets
├── docs/            Plan, instructions, pass logs, transcripts
│   ├── VIDEO_PLAN.md
│   ├── INSTRUCTIONS.md
│   ├── ASSET_INDEX.md
│   ├── TRANSCRIPTS.md
│   ├── VISUAL_DESCRIPTOR_WORKFLOW.md
│   └── PASS{2,3,4,5,7,8}_*.md
├── scripts/         Render pipeline + transcription
│   ├── make_contact_sheets.sh
│   ├── make_rough_review_cut{,_v2..v5}.sh
│   └── transcribe_all.py
├── audio/           Voiceovers, music beds, reference audio
│   ├── voiceovers/
│   ├── music/
│   └── reference_audio.wav
├── renders/         Output rough cuts
│   └── review_cuts/
├── piano hand size 2 video.fcpbundle/   Final Cut library (gitignored internals)
└── venv_transcribe/                     Whisper venv (gitignored)
```

Scripts self-cd to the `keyboard-trip/` root, so they can be invoked
from anywhere:

```bash
./keyboard-trip/scripts/make_rough_review_cut_v5.sh
```

Raw `.MOV`/`.mp4`/`.wav` are gitignored — only the structure, transcripts,
docs, scripts, and reference frames are tracked.

## ai-agent-video-editor/ layout

```
ai-agent-video-editor/
├── src/
│   ├── app/         Next.js routes
│   ├── components/  Timeline, clip view, notes panel
│   └── lib/
│       ├── db.ts          SQLite schema, migrations, render-job seed
│       ├── seed-data.ts   pianoProjectRoot, asset/timeline seeds
│       └── types.ts
├── docs/
│   ├── WORKFLOW.md
│   └── EDITOR_APP_PLAN.md
└── .cut-notes/      SQLite database (local, gitignored)
    └── cut-notes.sqlite
```

## How the editor finds the video files

The editor reads from `keyboard-trip/` via two configured paths:

1. **`pianoProjectRoot`** in `src/lib/seed-data.ts`:
   ```ts
   export const pianoProjectRoot =
     "/Users/lionelyu/Music/Piano Hand Size Part 2/keyboard-trip";
   ```
2. **`sourceRelativePaths`** in the same file maps clip basenames to
   paths relative to that root, e.g.
   `001_IMG_0256_0142am_trip_setup.MOV` →
   `footage/01_Trip_Setup/001_IMG_0256_0142am_trip_setup.MOV`.

On first run the editor seeds SQLite with absolute paths
(`pianoProjectRoot + sourceRelativePaths[basename]`) and stores them in
the `assets.path` column. If `keyboard-trip/` ever moves again, both
the constant in `seed-data.ts` and the cached paths in
`.cut-notes/cut-notes.sqlite` need to be updated.

## The review loop

1. A `make_rough_review_cut_v*.sh` script renders to
   `keyboard-trip/renders/review_cuts/`.
2. A new pass + render-job + timeline-items row is recorded in the
   editor's SQLite, pointing at that render and its
   `keyboard-trip/docs/PASS*.md` log.
3. Lionel opens the editor (`npm run dev` in `ai-agent-video-editor/`)
   and reviews the cut: scrubbing the timeline, watching the clip
   preview, leaving notes per pass and per timeline item.
4. The next AI pass reads the open notes, edits the next
   `make_rough_review_cut_v(N+1).sh` and the corresponding
   `PASS*_FIX_LOG.md`, renders, and writes a `fix_log` note back into
   the same project ledger.
5. Repeat until the rough cut is locked, then move to Final Cut Pro
   for finishing in the `.fcpbundle`.

## Working in this repo

Make changes inside the folder they belong to and commit there:

```bash
# video plan / footage / scripts / pass logs
cd keyboard-trip   (or just edit from repo root — outer repo tracks it)
git add … && git commit … && git push

# editor app code
cd ai-agent-video-editor
git add … && git commit … && git push
```
