#!/usr/bin/env python3
"""Render an mp4 directly from a pass yaml (no bash scripts needed).

Implements Plan Step 15 / Checklist item 15.

Minimal supported feature set (item 15):
  - video clips with sourceIn / sourceOut / rotation
  - still clips (JPG / PNG)
  - title cards (placeholder + title_card lanes)
  - voiceover audio (mixed at absolute timeline_start)
  - music beds (mixed with default ducking under VOs via volume notes)
  - explicit timelineStart for every visual; unknown timeline_start
    on audio is treated as silent

Item 18 expands this to caption boxes, montage fade-in/out, loudnorm,
multi-audio mix nuances, and per-clip duck windows; for now the
renderer is intentionally simple so item 17 can run it next to the
bash script for parallel comparison.

Usage:
  python3 scripts/render_from_timeline.py <pass-yaml> <output.mp4>
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

W = 1280
H = 720
FPS = 30
SR = 48000
FONT = (
    "/System/Library/Fonts/Supplemental/Arial.ttf"
    if Path("/System/Library/Fonts/Supplemental/Arial.ttf").exists()
    else "/System/Library/Fonts/Supplemental/Helvetica.ttf"
)


def _rotation_filter(rotation: int) -> str:
    """Convert numeric rotation (0/90/180/270 ccw degrees) to ffmpeg
    transpose filter chain."""
    rotation = (rotation or 0) % 360
    if rotation == 0:
        return ""
    if rotation == 90:
        return "transpose=1,"
    if rotation == 180:
        return "transpose=2,transpose=2,"
    if rotation == 270:
        return "transpose=2,"
    return ""


def _video_filter(rotation: int) -> str:
    return (
        f"{_rotation_filter(rotation)}"
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps={FPS},format=yuv420p"
    )


def _caption_filter(rotation: int, caption: str) -> str:
    """Lower-third caption box matching the bash script's
    `caption_filter` (drawbox + drawtext at y=586). Item 18: parity
    with v12's add_video_captioned helper."""
    safe = caption.replace(":", r"\:").replace("'", r"\'")
    return (
        _video_filter(rotation)
        + ",drawbox=x=76:y=560:w=1128:h=104:color=black@0.62:t=fill,"
        + f"drawtext=fontfile={FONT}:text='{safe}':fontcolor=white:"
        + "fontsize=34:line_spacing=8:x=(w-text_w)/2:y=586"
    )


def _resolve_path(rel: str) -> Path:
    """Resolve a clip's source.file to an absolute path."""
    candidate = REPO_ROOT / rel
    if candidate.exists():
        return candidate
    candidate = REPO_ROOT.parent / rel
    if candidate.exists():
        return candidate
    return Path(rel)


def _render_video_segment(
    src: Path, source_in: float, duration: float, rotation: int,
    out: Path, caption: str | None = None,
) -> None:
    vf = _caption_filter(rotation, caption) if caption else _video_filter(rotation)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{source_in}", "-i", str(src), "-t", f"{duration}",
        "-vf", vf,
        "-an",  # strip source audio; the audio mix happens separately
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def _render_still_segment(
    src: Path, duration: float, rotation: int, out: Path,
    caption: str | None = None,
) -> None:
    vf = _caption_filter(rotation, caption) if caption else _video_filter(rotation)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", str(src), "-t", f"{duration}",
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def _render_card_segment(text: str, duration: float, out: Path) -> None:
    """Black background with centered drawtext."""
    safe = text.replace(":", r"\:").replace("'", r"\'")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={duration}",
        "-vf",
        f"drawtext=fontfile={FONT}:text='{safe}':fontcolor=white:fontsize=44:"
        "x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=10",
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        str(out),
    ]
    subprocess.run(cmd, check=True)


def _concat_segments(segment_files: list[Path], concat_file: Path, out: Path) -> None:
    with concat_file.open("w") as fh:
        for seg in segment_files:
            fh.write(f"file '{seg}'\n")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def _build_audio_mix(
    audio_clips: list[dict], runtime: float, work_dir: Path, out: Path
) -> None:
    """Mix every voiceover/music clip at its absolute timeline position
    onto a stereo base of `runtime` seconds.

    Item 18: VOs are pre-rendered to intermediate WAVs with loudnorm
    applied per-file (sequential, fast). The final mix step then only
    needs adelay + amix, no per-clip filtering — keeps the filter graph
    small even with 18+ audio clips.
    """
    if not audio_clips:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i",
            f"anullsrc=channel_layout=stereo:sample_rate={SR}",
            "-t", f"{runtime}",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2",
            str(out),
        ]
        subprocess.run(cmd, check=True)
        return

    audio_dir = work_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    intermediates: list[tuple[Path, float, float]] = []  # (file, start_s, volume)
    for i, c in enumerate(audio_clips):
        src = _resolve_path(c["source"]["file"])
        sin = float((c["source"].get("in") or 0.0))
        sout = float((c["source"].get("out") or 0.0)) or float(c["timeline"]["duration"])
        seg_dur = max(0.0, sout - sin) if sout > sin else float(c["timeline"]["duration"])
        ts = float(c["timeline"]["start"])

        volume = 1.0
        notes = (c.get("notes") or "")
        if "[audio: volume=" in notes:
            try:
                volume = float(
                    notes.split("[audio: volume=", 1)[1].split("]", 1)[0]
                )
            except ValueError:
                volume = 1.0
        if "[audio: muted]" in notes:
            volume = 0.0
        if c.get("track") == "music" and volume == 1.0:
            volume = 0.32

        inter = audio_dir / f"a_{i:03d}.wav"
        per_clip_filters = [
            f"aresample={SR}",
            "aformat=channel_layouts=stereo",
        ]
        if c.get("track") == "voiceover":
            per_clip_filters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
        if c.get("track") == "aroll":
            # 0.4s audio fade-out at the end (matches bash add_video).
            fade_start = max(0.0, seg_dur - 0.4)
            per_clip_filters.append(
                f"afade=t=out:st={fade_start}:d=0.4"
            )
        per_clip_chain = ",".join(per_clip_filters)
        # Use -map 0:a:0? so videos with no audio stream don't error;
        # they produce silence and the mix step proceeds fine.
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{sin}", "-i", str(src), "-t", f"{seg_dur}",
            "-af", per_clip_chain,
            "-map", "0:a:0?",
            "-c:a", "pcm_s16le", "-ar", str(SR), "-ac", "2",
            str(inter),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # No audio stream (e.g. a still routed through here) — write
            # silence of the right length so the mix step still works.
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i",
                    f"anullsrc=channel_layout=stereo:sample_rate={SR}",
                    "-t", f"{seg_dur}",
                    "-c:a", "pcm_s16le",
                    str(inter),
                ],
                check=True,
            )
        intermediates.append((inter, ts, volume))

    # Mix the intermediates with adelay + amix (lightweight filter
    # graph: no per-clip filtering, just delay + volume + sum).
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for i, (path, ts, volume) in enumerate(intermediates):
        delay_ms = int(ts * 1000)
        inputs += ["-i", str(path)]
        filters.append(
            f"[{i}:a]adelay={delay_ms}|{delay_ms},volume={volume}[a{i}]"
        )
        labels.append(f"[a{i}]")
    n = len(intermediates)
    # normalize=0 stops amix from dividing every input by N, which would
    # crush an 18-clip mix by ~25 dB. Per-clip volume is already shaped
    # via the volume= step above (VO=1.0, music=0.32 default), so the
    # sum is already at proper levels.
    mix = (
        f"{''.join(labels)}amix=inputs={n}:duration=longest"
        f":dropout_transition=0:normalize=0,"
        f"alimiter=limit=0.95,"
        f"apad,atrim=duration={runtime}[aout]"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", f"{';'.join(filters)};{mix}",
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def _mux(video: Path, audio: Path, out: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def render(pass_yaml: Path, out_mp4: Path) -> None:
    dump = yaml.safe_load(pass_yaml.read_text())
    runtime = float(dump["summary"]["total_duration_seconds"])
    active_visual = dump["active_visual"]
    clips_by_id = {c["id"]: c for c in dump["clips"]}

    work = Path(tempfile.mkdtemp(prefix="render-from-timeline-"))
    seg_dir = work / "segments"
    seg_dir.mkdir()
    print(f"[work] {work}")

    segment_files: list[Path] = []
    for i, seg in enumerate(active_visual):
        clip = clips_by_id.get(seg["clip_id"])
        if clip is None:
            print(f"[warn] segment references missing clip {seg['clip_id']}", file=sys.stderr)
            continue
        out_seg = seg_dir / f"seg_{i:04d}.mp4"
        duration = float(seg["window"][1]) - float(seg["window"][0])
        rotation = int(clip.get("rotation") or 0)
        track = clip.get("track")
        src_rel = (clip.get("source") or {}).get("file") or ""
        caption = clip.get("text_overlay") or None
        if track in ("title_card", "placeholder") or not src_rel:
            text = caption or clip.get("notes") or seg["clip_id"]
            _render_card_segment(str(text), duration, out_seg)
        else:
            src = _resolve_path(src_rel)
            sin = float((clip["source"].get("in") or 0.0))
            if seg.get("lane") == "still" or src.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                _render_still_segment(src, duration, rotation, out_seg, caption=caption)
            else:
                _render_video_segment(src, sin, duration, rotation, out_seg, caption=caption)
        segment_files.append(out_seg)

    print(f"[concat] {len(segment_files)} visual segments → silent mp4")
    silent_video = work / "video_silent.mp4"
    concat_file = work / "concat.txt"
    _concat_segments(segment_files, concat_file, silent_video)

    audio_clips = [
        c for c in dump["clips"] if c.get("track") in ("voiceover", "music")
    ]
    # Include source audio from a_roll visual segments (Lionel's
    # talking-head dialogue). Without this, ~half the cut renders
    # silent because the cold open + main argument + home payoff are
    # all a_roll with no separate VO. Lane convention (set in item 4):
    # only a_roll plays its source audio at render time; ambient /
    # b_roll / still / title_card / placeholder are silent cover.
    aroll_audio_clips = []
    for seg in active_visual:
        if seg.get("lane") != "a_roll":
            continue
        clip = clips_by_id.get(seg["clip_id"])
        if not clip:
            continue
        src_rel = (clip.get("source") or {}).get("file") or ""
        if not src_rel:
            continue
        ext = src_rel.rsplit(".", 1)[-1].lower()
        if ext in {"jpg", "jpeg", "png"}:
            continue
        if "[audio: muted]" in (clip.get("notes") or ""):
            continue
        # Compute the correct source_in for THIS sub-window of the
        # clip: clip start in source coords + offset of segment within
        # the clip's timeline window.
        clip_tl_start = float(clip["timeline"]["start"])
        clip_source_in = float((clip["source"].get("in") or 0.0))
        seg_tl_start = float(seg["window"][0])
        seg_dur = float(seg["window"][1]) - seg_tl_start
        sub_source_in = clip_source_in + max(0.0, seg_tl_start - clip_tl_start)
        aroll_audio_clips.append(
            {
                "id": f"aroll-{seg['clip_id']}-{seg_tl_start:.3f}",
                "track": "aroll",
                "source": {"file": src_rel, "in": sub_source_in,
                           "out": sub_source_in + seg_dur},
                "timeline": {"start": seg_tl_start, "duration": seg_dur},
                "notes": clip.get("notes"),
            }
        )

    all_audio = audio_clips + aroll_audio_clips
    print(
        f"[audio] mixing {len(audio_clips)} VO/music + "
        f"{len(aroll_audio_clips)} a-roll source-audio segments "
        f"over {runtime:.2f}s"
    )
    audio_mix = work / "audio_mix.aac"
    _build_audio_mix(all_audio, runtime, work, audio_mix)

    print(f"[mux] → {out_mp4}")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    _mux(silent_video, audio_mix, out_mp4)

    # Probe duration to confirm
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    actual = float(probe.stdout.strip())
    print(f"[done] runtime expected={runtime:.2f}s actual={actual:.2f}s")
    if abs(actual - runtime) > 0.5:
        print(f"[warn] duration drift {abs(actual-runtime):.2f}s exceeds 0.5s tolerance")

    # Optional cleanup
    if not _keep_workdir():
        shutil.rmtree(work, ignore_errors=True)


def _keep_workdir() -> bool:
    import os
    return bool(os.environ.get("KEEP_WORKDIR"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pass_yaml", type=Path)
    parser.add_argument("out_mp4", type=Path)
    args = parser.parse_args()
    if not args.pass_yaml.exists():
        print(f"error: pass yaml not found: {args.pass_yaml}", file=sys.stderr)
        return 1
    render(args.pass_yaml, args.out_mp4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
