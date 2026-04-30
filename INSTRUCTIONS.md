# Project Instructions: Piano Hand Size Part 2

This file documents the working system for turning the local assets into the YouTube video described in `VIDEO_PLAN.md`.

## North Star

Use `VIDEO_PLAN.md` as the creative source of truth.

The video is a story-driven explainer:

> I drove through the night to pick up rare DS 6.0 and DS 5.5 piano keyboards because hand size changes the entire way you experience the piano.

The trip gives the video movement. The hand-size / DS-keyboard argument gives it meaning.

Target length: 10 to 13 minutes.

## Current Asset Organization

The project has been reorganized into chronological edit bins:

- `01_Trip_Setup`
- `02_Drive_To_Titusville`
- `03_David_Factory_Visit`
- `04_Keyboards_Technical_Stills`
- `05_Post_Pickup_Main_Argument`
- `06_Car_Trouble_Return`
- `07_Home_Demo_Payoff`
- `08_Pickups_To_Record`
- `90_Reference_Frames`
- `91_Visual_Contact_Sheets`

Use `ASSET_INDEX.md` for the complete asset list.

Videos were renamed chronologically while preserving the original camera ID:

```text
001_IMG_0256_0142am_trip_setup.MOV
013_IMG_0269_keyboard_21_intro.MOV
054_IMG_0310_home_ds60_ds55_explanation.MOV
```

Each video should have a matching transcript with the same basename:

```text
013_IMG_0269_keyboard_21_intro.MOV
013_IMG_0269_keyboard_21_intro.txt
```

Do not rename assets casually after this point. The edit plan, transcripts, contact sheets, and future moment lists all depend on these names.

## Transcripts

All current `.MOV` clips have matching `.txt` transcripts. `IMG_0310.MOV` has already been transcribed and lives at:

```text
07_Home_Demo_Payoff/054_IMG_0310_home_ds60_ds55_explanation.txt
```

Use `transcribe_all.py` when new clips are added, especially the pickup clips in `08_Pickups_To_Record`.

Default behavior: skip transcripts that already exist.

```bash
python3 transcribe_all.py
```

Force regeneration only when needed:

```bash
python3 transcribe_all.py --force
```

After transcript files are edited, regenerate `TRANSCRIPTS.md` so the master transcript reflects the current clip notes.

```bash
{
  printf '# Master Timestamped Transcripts: Piano Hand Size Part 2\n\n'
  current=''
  find 01_Trip_Setup 02_Drive_To_Titusville 03_David_Factory_Visit 05_Post_Pickup_Main_Argument 06_Car_Trouble_Return 07_Home_Demo_Payoff 08_Pickups_To_Record -type f -name '*.txt' | sort | while IFS= read -r file; do
    dir=${file%/*}
    base=${file##*/}
    name=${base%.txt}
    if [ "$dir" != "$current" ]; then
      printf '\n## %s\n\n' "$dir"
      current="$dir"
    fi
    printf '### %s\n' "$name"
    sed -n '1,999p' "$file"
    printf '\n\n'
  done
} > /private/tmp/TRANSCRIPTS.new
mv /private/tmp/TRANSCRIPTS.new TRANSCRIPTS.md
```

## Visual Review Workflow

For the first edit pass, use fixed 2-second contact sheets instead of PySceneDetect.

Reason:

- Most clips are continuous phone footage, not edited footage with hard cuts.
- PySceneDetect finds camera/scene cuts, but many clips have no cuts.
- A 2-second grid gives enough visual context to understand beginning, middle, and end.
- This is better for b-roll, keyboard close-ups, road footage, and clips where the transcript is unclear.

Contact sheets live in:

```text
91_Visual_Contact_Sheets/
```

Regenerate the current 2-second review sheets with:

```bash
./make_contact_sheets.sh 2
```

Use a 1-second pass only for clips that need closer inspection:

```bash
./make_contact_sheets.sh 1
```

PySceneDetect can still be useful later for long, visually varied clips, but it is not required for the current pass.

## Transcript File Format

Every video transcript can include a visual descriptor above the dialogue transcript.

Use this format:

```text
## Visual Scene Descriptor

Beginning: ...
Middle: ...
End: ...

Editor note: ...

## Dialogue Transcript

[00:00] ...
```

Descriptors should be factual and useful for editing. They should answer:

- What are we looking at?
- How does the shot change from beginning to middle to end?
- What is the clip useful for?

Helpful editor labels:

- `talking_head`: person speaking directly or narrating while filming.
- `broll`: visual material usable under voiceover or as a cutaway.
- `ambient`: mood, scenery, room tone, or travel texture.
- `proof`: shows the keyboard, size comparison, hand position, mechanical detail, or real-world evidence.
- `backup`: potentially usable but not essential.

## Edit Passes

### Pass 0: Plan

Already done in `VIDEO_PLAN.md`.

This sets the thesis, structure, tone, and rough time allocation. Treat it as the current north star.

### Pass 1: Visual Descriptor Pass

Goal: enrich each `.txt` transcript with beginning/middle/end visual context from the contact sheets.

Do not make edit-order decisions in this pass. Just describe what is visible and what the clip may be useful for.

For clips where the dialogue already explains the moment clearly, descriptors can be short. For clips with unclear dialogue, sparse transcript, road footage, keyboard close-ups, or technical demonstrations, descriptors should be more specific.

### Pass 2: Moment Shortlist

Goal: make a generous unordered shortlist of usable moments.

For each clip, use:

- The transcript.
- The visual descriptor.
- The relevant contact sheet path.
- The beat it might serve from `VIDEO_PLAN.md`.

A moment can be:

- A transcript span.
- A visual shot or b-roll span.
- A combined audio/visual micro-sequence.

Return moments in this shape:

```json
{
  "clip": "03_David_Factory_Visit/018_IMG_0274_ds_size_lineup_on_steinway.MOV",
  "start": 42,
  "end": 58,
  "type": "talking_head | broll | ambient",
  "serves_beat": "Arrival and David's Keyboard World",
  "reason": "Shows the DS size lineup clearly.",
  "strength": "strong | useful | backup"
}
```

Important: Pass 2 is not the edit. Do not propose final order yet. Do not over-trim moments yet. Be generous, roughly 3-4x more material than the final video will use.

### Pass 3: Paper Edit

Goal: turn the shortlist into a rough ordered edit.

This is where the video structure becomes concrete:

- Cold open.
- Setup.
- Drive.
- Factory / David.
- Main argument.
- Car trouble.
- Home payoff.

Use `VIDEO_PLAN.md` as the spine, but let the strongest moments determine the exact flow.

### Pass 4: Assembly Notes

Goal: produce practical editor instructions:

- Exact clip order.
- Approximate trims.
- B-roll overlays.
- On-screen labels.
- Music / pacing notes.
- Where to insert the two pickup clips.

## Pickup Clips Still To Record

Folder:

```text
08_Pickups_To_Record/
```

Planned clips:

- `055_PICKUP_front_facing_intro.MOV`
- `056_PICKUP_hand_key_comparison.MOV`

Use `08_Pickups_To_Record/README.md` for the recording prompts.

After recording:

1. Put the clips in `08_Pickups_To_Record/`.
2. Run `python3 transcribe_all.py`.
3. Run `./make_contact_sheets.sh 2`.
4. Add visual descriptors to the new `.txt` files.
5. Regenerate `TRANSCRIPTS.md`.

## Working Rules

- Keep original `IMG_####` IDs in filenames.
- Keep chronological numeric prefixes.
- Keep one `.txt` transcript per `.MOV`.
- Add visual descriptors to transcript files, not separate sidecar files.
- Use contact sheets for visual understanding before making semantic edit choices.
- Use `VIDEO_PLAN.md` for structure, `ASSET_INDEX.md` for inventory, and `TRANSCRIPTS.md` for combined text review.
- Avoid letting Pass 1 or Pass 2 become the final edit too early.
