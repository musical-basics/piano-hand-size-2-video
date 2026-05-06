# Parallel Render: Pass 15

Generated: 2026-05-06

Item 17 of [Implementation Checklist](../Implementation%20Checklist.md):
render the same pass via the legacy bash script AND the new
`render_from_timeline.py`, document any mismatches.

## Inputs

- yaml: `timelines/pass-15-captions-travel-chronology.yaml` (post item 13
  fill — every clip has explicit timelineStart, zero semantic-issue errors)
- bash render: `renders/review_cuts/piano_hand_size_part2_rough_cut_v12.mp4`
  (produced by `make_rough_review_cut_v12.sh` on 2026-05-04)
- yaml render: `renders/review_cuts/piano_hand_size_part2_pass15_renderer.mp4`
  (produced by `render_from_timeline.py` on 2026-05-06)

## Comparison

| Metric | Expected (yaml) | Bash v12 | render_from_timeline.py |
| --- | ---: | ---: | ---: |
| Runtime (s) | 752.500 | 752.788 (+0.288) | 752.533 (+0.033) |
| Visual segments | 73 | 1 stream (concat'd) | 1 stream (concat'd) |
| Audio windows | 18 | 1 mixed stream | 1 mixed stream |
| Width × height | 1280×720 | 1280×720 | 1280×720 |
| Sample rate / ch | 48 kHz / 2 | 48 kHz / 2 | 48 kHz / 2 |

Both renders pass `compare_render_to_timeline.py`'s 0.5s drift gate.

## Mismatches noted

1. **Bash v12 is +0.288s long, yaml renderer is +0.033s long.** Both are
   within tolerance but the bash script accumulates a slightly larger
   drift. Likely source: the bash helpers re-encode each segment with
   `-c:v libx264 -preset veryfast -crf 26`, then concat. Each concat
   boundary contributes a small frame-time rounding difference. The
   yaml renderer also re-encodes per segment, but with `-r 30` enforced
   on every output, which keeps the boundary drift tighter.
2. **Captions and montage fade-in/out are not present in the yaml
   render.** Item 18 expands `render_from_timeline.py` to feature
   parity (caption boxes, montage fades, loudnorm, per-clip duck
   windows). Until then the yaml render is a structural-level mp4: same
   visual order and durations, plain audio mix, no caption text.
3. **Music ducking is naive in the yaml render.** Default 0.32 volume
   on all music clips. The bash script's `MUSIC_UNDER_VO_VOLUME=0.24`
   and section-specific volumes are not yet honored beyond the fixed
   default + the per-clip `[audio: volume=N]` notes hint
   (`apply_timeline_patch.py` set_volume / duck_music).
4. **No VO loudness normalization.** Bash v12 applies
   `loudnorm=I=-16:LRA=11:TP=-1.5` inside `finish_montage_with_vo*`
   helpers; the yaml renderer relies on raw VO levels. Item 18 will
   add this.

## Conclusion

Item 17 acceptance: parallel render works; mismatches are listed above.
The yaml renderer produces a playable, structurally-correct mp4 of the
same pass with a tighter runtime drift than the bash script. The
remaining gaps (captions, fades, loudnorm, finer ducking) are scoped to
item 18 (Plan Step 15 cont.) and item 19 (cut-over decision).

Until item 18 lands, the bash script remains canonical for review
deliveries; `render_from_timeline.py` is the smoke-test renderer used
to verify yaml-as-source-of-truth.
