# Visual Descriptor Workflow

Use this when the dialogue transcript does not explain what is visually happening.

## Current Choice

Use fixed 2-second contact sheets before PySceneDetect.

Why:

- Most clips are continuous phone footage, not edited footage with hard cuts.
- PySceneDetect finds visual cuts, but many of these clips have no cuts.
- A fixed 2-second grid gives enough visual context for the AI/editor to identify beginning, middle, and end.
- This works especially well for b-roll, keyboard close-ups, road footage, and unclear transcripts.

PySceneDetect can still be useful later for very long or visually varied clips, but it is not necessary for the first edit pass.

## Generated Contact Sheets

Contact sheets live in:

`footage/91_Visual_Contact_Sheets/`

Each clip has its own folder. Each sheet samples the video every 2 seconds and burns the timestamp into the thumbnail.

Regenerate with:

```bash
./scripts/make_contact_sheets.sh 2
```

Use a denser pass only when needed:

```bash
./scripts/make_contact_sheets.sh 1
```

## Transcript Format

When adding visual notes to a clip transcript, use this structure:

```text
## Visual Scene Descriptor

Beginning: ...
Middle: ...
End: ...

Editor note: ...

## Dialogue Transcript

[00:00] ...
```

Keep descriptors factual and editor-useful. They should answer: what are we looking at, how does the shot change, and what is the clip good for?

## Descriptor Types

Use these labels in editor notes when helpful:

- `talking_head`: person speaking directly or narrating while filming.
- `broll`: visual material useful under voiceover or as a cutaway.
- `ambient`: mood, travel texture, scenery, room tone, or atmosphere.
- `proof`: shows the object, place, keyboard, size comparison, hand position, or mechanical detail.
- `backup`: potentially usable, but not essential.

## Recommended Pass 1 Input

For each clip, combine:

- The clip transcript.
- Its visual scene descriptor.
- The relevant contact sheet path.
- The `VIDEO_PLAN.md` beat it might serve.

Then shortlist moments generously without ordering them yet.
