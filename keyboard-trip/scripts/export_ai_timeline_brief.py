#!/usr/bin/env python3
"""Export a compact AI-readable brief of the current pass timeline.

The brief is what an AI agent should read FIRST, before pulling the full
per-pass dump. It distills the pass into the minimum signal an agent
needs to plan an `edit_patch_plan.json` (Implementation Plan step 7,
checklist item 3):

  - pass_id, runtime, clip_count
  - issues_summary  — counts from the dump's issues block
  - locked_clips    — ids that the user has manually edited (do not touch)
  - story_beats     — each beat from STORY_BEATS.yaml with the clip_ids
                      that fall inside it, plus how much of the beat is
                      covered and what story_phases actually appeared
  - active_visual   — compact [start, end, clip_id, lane] rows
  - audio_windows   — voiceovers and music windows separately
  - problem_flags   — placeholder for the semantic validator (item 4)

Usage:
  python3 scripts/export_ai_timeline_brief.py <pass-id>

  Writes timelines/<pass-id>-ai-brief.yaml. Pass-id matches the
  filename stem in timelines/, e.g. pass-15-captions-travel-chronology.

Done-when (checklist item 3): runs cleanly on the current pass, output
is materially smaller than the full dump, and a human glance shows it
is actionable on its own.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMELINES_DIR = REPO_ROOT / "timelines"
DOCS_DIR = REPO_ROOT / "docs"
ASSET_INTELLIGENCE_PATH = DOCS_DIR / "ASSET_INTELLIGENCE.yaml"
STORY_BEATS_PATH = DOCS_DIR / "STORY_BEATS.yaml"


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def _build_basename_to_phase() -> dict[str, str]:
    """Map source file basename → story_phase from ASSET_INTELLIGENCE."""
    ai = _load_yaml(ASSET_INTELLIGENCE_PATH)
    out: dict[str, str] = {}
    for asset in ai.get("assets", []):
        file_path = asset.get("file", "")
        if file_path.startswith("synthetic://"):
            continue
        basename = file_path.split("/")[-1]
        out[basename] = asset["story_phase"]
    return out


def _segment_beat(beats: list[dict], start: float, end: float) -> dict | None:
    """Return the beat that fully contains [start, end), or None."""
    for beat in beats:
        if beat["start"] <= start < beat["end"] and end <= beat["end"] + 1e-6:
            return beat
    return None


def _round(value: float, places: int = 3) -> float:
    return round(float(value), places)


def build_brief(pass_id: str) -> dict:
    pass_yaml_path = TIMELINES_DIR / f"{pass_id}.yaml"
    if not pass_yaml_path.exists():
        raise FileNotFoundError(f"pass yaml not found: {pass_yaml_path}")

    dump = _load_yaml(pass_yaml_path)
    beats_doc = _load_yaml(STORY_BEATS_PATH)
    basename_to_phase = _build_basename_to_phase()

    pass_meta = dump.get("pass", {})
    summary = dump.get("summary", {})
    runtime = float(summary.get("total_duration_seconds") or 0.0)
    clips: list[dict] = dump.get("clips", [])
    active_visual: list[dict] = dump.get("active_visual", [])
    issues_block: dict = dump.get("issues", {})

    beats = beats_doc.get("beats", [])

    # --- locked clips -------------------------------------------------
    locked_clips = sorted(
        c["id"] for c in clips if c.get("last_edited_by") == "user"
    )

    # --- story beats with membership ---------------------------------
    beats_brief = []
    av_index_by_beat: dict[str, list[dict]] = {b["id"]: [] for b in beats}
    for seg in active_visual:
        start, end = seg["window"]
        beat = _segment_beat(beats, float(start), float(end))
        if beat is not None:
            av_index_by_beat[beat["id"]].append(seg)

    for beat in beats:
        members = av_index_by_beat[beat["id"]]
        clip_ids = [m["clip_id"] for m in members]
        coverage = sum(m["window"][1] - m["window"][0] for m in members)
        # which actual story_phases appeared (so an agent sees mix at a glance)
        observed_phases: set[str] = set()
        for m in members:
            src = m.get("source") or ""
            if not src:
                continue
            phase = basename_to_phase.get(src.split("/")[-1])
            if phase:
                observed_phases.add(phase)
        beats_brief.append(
            {
                "id": beat["id"],
                "window": [_round(beat["start"]), _round(beat["end"])],
                "purpose": beat.get("purpose", "").strip(),
                "allowed_story_phases": list(beat["allowed_story_phases"]),
                "observed_story_phases": sorted(observed_phases),
                "clip_count": len(clip_ids),
                "coverage_seconds": _round(coverage, 2),
                "clip_ids": clip_ids,
            }
        )

    # --- compact active_visual ---------------------------------------
    compact_av = [
        [
            _round(seg["window"][0], 3),
            _round(seg["window"][1], 3),
            seg["clip_id"],
            seg.get("lane", ""),
        ]
        for seg in active_visual
    ]

    # --- audio windows ------------------------------------------------
    voiceovers = []
    music = []
    for c in clips:
        track = c.get("track")
        if track not in ("voiceover", "music"):
            continue
        tl = c.get("timeline", {})
        src = (c.get("source") or {}).get("file", "")
        entry = {
            "clip_id": c["id"],
            "window": [_round(tl.get("start", 0.0)), _round(tl.get("end", 0.0))],
            "duration": _round(tl.get("duration", 0.0), 3),
            "file": src.split("/")[-1] if src else "",
        }
        if track == "voiceover":
            voiceovers.append(entry)
        else:
            music.append(entry)
    voiceovers.sort(key=lambda e: e["window"][0])
    music.sort(key=lambda e: e["window"][0])

    # --- issues_summary ----------------------------------------------
    issues_summary = {
        "overlaps": len(issues_block.get("overlaps", [])),
        "gaps": len(issues_block.get("gaps", [])),
        "audio_collisions": len(issues_block.get("audio_collisions", [])),
        "source_overruns": len(issues_block.get("source_overruns", [])),
    }

    # --- problem_flags ------------------------------------------------
    # Reserved for the semantic validator (item 4). Populate stub flags
    # the brief consumer can already act on (e.g. clips with no source).
    problem_flags: list[dict] = []
    for c in clips:
        if not (c.get("source") or {}).get("file") and c.get("track") not in (
            "title_card",
            "placeholder",
        ):
            problem_flags.append(
                {
                    "code": "MISSING_SOURCE",
                    "clip_id": c["id"],
                    "message": "clip has no source file but is not a title_card/placeholder",
                }
            )

    brief = {
        "pass_id": pass_id,
        "pass_name": pass_meta.get("name"),
        "pass_status": pass_meta.get("status"),
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "source_pass_yaml": str(pass_yaml_path.relative_to(REPO_ROOT)),
        "runtime_seconds": _round(runtime, 2),
        "clip_count": int(summary.get("clips") or len(clips)),
        "active_visual_segments": int(
            summary.get("active_visual_segments") or len(active_visual)
        ),
        "issues_summary": issues_summary,
        "locked_clips": locked_clips,
        "story_beats": beats_brief,
        "audio_windows": {"voiceovers": voiceovers, "music": music},
        "active_visual": compact_av,
        "problem_flags": problem_flags,
    }
    return brief


def write_brief(pass_id: str) -> Path:
    brief = build_brief(pass_id)
    out_path = TIMELINES_DIR / f"{pass_id}-ai-brief.yaml"
    with out_path.open("w") as fh:
        # default_flow_style=None lets short lists render inline (compact)
        # while complex ones stay block — best of both.
        yaml.safe_dump(
            brief,
            fh,
            sort_keys=False,
            default_flow_style=None,
            width=100,
            allow_unicode=True,
        )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "pass_id",
        help="Pass id (filename stem in timelines/, e.g. pass-15-captions-travel-chronology)",
    )
    args = parser.parse_args()

    try:
        out_path = write_brief(args.pass_id)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    full_dump = TIMELINES_DIR / f"{args.pass_id}.yaml"
    full_lines = sum(1 for _ in full_dump.open())
    brief_lines = sum(1 for _ in out_path.open())
    ratio = full_lines / brief_lines if brief_lines else float("inf")
    print(
        f"wrote {out_path.relative_to(REPO_ROOT)}  "
        f"({brief_lines} lines vs {full_lines} in full dump, {ratio:.1f}× smaller)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
