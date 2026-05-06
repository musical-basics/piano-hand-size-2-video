#!/usr/bin/env python3
"""Sanity-check a rendered mp4 against the pass yaml that produced it.

Implements Plan Step 17 / Checklist item 16.

Checks:
  1. expected runtime (from yaml summary) vs actual runtime (ffprobe).
     Errors if drift > 0.5s.
  2. expected number of visual segments (active_visual length) — printed.
  3. expected audio window count (clips on voiceover + music tracks) —
     printed and probed against the rendered mp4's audio stream count.

Usage:
  python3 scripts/compare_render_to_timeline.py <pass-yaml> <render.mp4>

Exit codes:
  0  drift within tolerance
  1  drift > 0.5s
  2  invocation problem
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

DURATION_TOLERANCE = 0.5


def _ffprobe_format(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def compare(pass_yaml: Path, render_mp4: Path) -> int:
    dump = yaml.safe_load(pass_yaml.read_text())
    expected_runtime = float(dump["summary"]["total_duration_seconds"])
    expected_segments = len(dump.get("active_visual", []))
    audio_clips = [
        c for c in dump.get("clips", [])
        if c.get("track") in ("voiceover", "music")
    ]
    expected_audio_windows = len(audio_clips)

    info = _ffprobe_format(render_mp4)
    actual_runtime = float(info["format"]["duration"])
    streams = info.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    video_streams = [s for s in streams if s.get("codec_type") == "video"]

    drift = actual_runtime - expected_runtime

    print(f"yaml:    {pass_yaml.relative_to(pass_yaml.parent.parent.parent) if pass_yaml.is_absolute() else pass_yaml}")
    print(f"render:  {render_mp4}")
    print()
    print(f"runtime expected = {expected_runtime:.3f}s")
    print(f"runtime actual   = {actual_runtime:.3f}s")
    print(f"runtime drift    = {drift:+.3f}s (tolerance ±{DURATION_TOLERANCE}s)")
    print()
    print(f"visual segments expected (yaml active_visual rows):  {expected_segments}")
    print(f"audio windows expected (yaml VO + music clips):      {expected_audio_windows}")
    print(f"video streams in render:                             {len(video_streams)}")
    print(f"audio streams in render:                             {len(audio_streams)}")

    if abs(drift) > DURATION_TOLERANCE:
        print(
            f"\nERROR: runtime drift {drift:+.3f}s exceeds tolerance "
            f"±{DURATION_TOLERANCE}s",
            file=sys.stderr,
        )
        return 1

    print("\nOK — runtime within tolerance")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pass_yaml", type=Path)
    parser.add_argument("render_mp4", type=Path)
    args = parser.parse_args()
    if not args.pass_yaml.exists():
        print(f"error: pass yaml not found: {args.pass_yaml}", file=sys.stderr)
        return 2
    if not args.render_mp4.exists():
        print(f"error: render mp4 not found: {args.render_mp4}", file=sys.stderr)
        return 2
    return compare(args.pass_yaml, args.render_mp4)


if __name__ == "__main__":
    sys.exit(main())
