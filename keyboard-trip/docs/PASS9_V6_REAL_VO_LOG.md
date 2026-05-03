# Pass 9 V6 Real VO + Extended Montage Log

Output:

```text
keyboard-trip/renders/review_cuts/piano_hand_size_part2_rough_cut_v6.mp4
```

Runtime:

```text
11:38
```

Specs:

```text
1280x720, 30 fps, H.264 video, AAC audio, 132 MB
```

## Changes Applied

- VO_01 is now Lionel's real recording from a Logic session bounce
  (`Piano Hand Size Part 2 Audio.wav`, 39.91s) instead of Cartesia TTS.
- Updated VO_01 transcript in `audio/voiceovers/TRAVEL_VO_SCRIPT.md` to
  match what Lionel actually said: "narrower keys can change…",
  "On paper this sounds ridiculous", "the entire experience".
- Cartesia voice clone was deleted and re-cloned from Lionel's real
  recording for vocal consistency on VO_02..VO_06. New voice id:
  `cba3c82a-4099-489c-acb0-4e927e89eeed`.
- Regenerated VO_02..VO_06 with the new voice using `sonic-3`.
- Extended the VO_01 montage from ~23s to ~40s to fit the longer real
  recording. New visual sequence:
  1. IMG_0256 selfie still (4s)
  2. IMG_0286 keyboard close-up still (5s ccw)
  3. IMG_0264 Pennsylvania scenery video (5s)
  4. IMG_0259 sheets stop video (5s)
  5. IMG_0274 DS size lineup video (10s ccw)
  6. IMG_0287 keyboard detail still (4s ccw)
  7. IMG_0288 keyboard detail still (4s ccw)
  8. IMG_0290 keyboard detail still (3s ccw)
- Saved the VO regeneration workflow as
  `scripts/regenerate_voiceovers.py` so it can be re-run on demand.

## Verification

```text
duration: 698.147500
video: h264, 1280x720, 30 fps
audio: aac, 48000 Hz, stereo
size: ~132 MB
```

VO durations after regeneration:

```text
VO_01_late_night_drive.wav        39.91s   (real recording)
VO_02_gas_station_and_snacks.wav  17.28s   (Cartesia TTS, sonic-3)
VO_03_car_nap.wav                 14.40s   (Cartesia TTS, sonic-3)
VO_04_pennsylvania_road.wav       18.39s   (Cartesia TTS, sonic-3)
VO_05_lake_pause.wav              10.68s   (Cartesia TTS, sonic-3)
VO_06_breakdown_and_return.wav    17.65s   (Cartesia TTS, sonic-3)
```

## Known Rough Edges

- Whole cut shifts +17s vs v5 because of the longer VO_01 montage; any
  external timing references (chapter markers, etc.) need to be re-checked.
- VO_02..VO_06 are still Cartesia TTS. They sound closer to Lionel's
  real voice now (cloned from a longer, cleaner sample) but the seams
  between real-Lionel and TTS-Lionel may still be audible.
- The new VO_01 montage relies on more keyboard close-up stills. Pacing
  is more contemplative; trim individual still durations if it feels slow.
- P056 hand/key comparison pickup is still a placeholder card.
- Music bed is still the procedural `pass8_travel_bed.wav` placeholder.
