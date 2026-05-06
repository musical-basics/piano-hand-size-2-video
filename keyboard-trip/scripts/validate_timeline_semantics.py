#!/usr/bin/env python3
"""Run semantic validators against the current pass.

Implements Plan Steps 9-13 (checklist items 4 + 5):

  CHRONOLOGY_ERROR              active visual's story_phase not in
                                current beat's allowed_story_phases
  STILL_UNDER_VO_WARNING        a still is the active visual under a VO
                                for >6 seconds
  VO_CUTOFF_ERROR               visual coverage under a VO is shorter than
                                vo_duration + 0.4s safety margin
  DIALOGUE_COLLISION_WARNING    VO is active and underlying a-roll has
                                has_dialogue=true and source audio is not
                                explicitly muted/ducked (notes heuristic)
  MISSING_TIMELINE_START_ERROR  enabled clip has NULL timelineStart in DB
  PACING_WARNING                continuous VO+broll block runs >20s with
                                no a-roll burst, title card, or major
                                visual change

Usage:
  python3 scripts/validate_timeline_semantics.py <pass-id>

Reads:
  - timelines/<pass-id>.yaml
  - docs/STORY_BEATS.yaml
  - docs/ASSET_INTELLIGENCE.yaml
  - ../ai-agent-video-editor/.cut-notes/cut-notes.sqlite (read-only)

Writes:
  - timelines/<pass-id>-semantic-issues.yaml

Exit code:
  0  no errors (warnings allowed)
  1  one or more *_ERROR issues found
  2  invocation problem (missing pass yaml, etc.)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sqlite3
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMELINES_DIR = REPO_ROOT / "timelines"
DOCS_DIR = REPO_ROOT / "docs"
ASSET_INTELLIGENCE_PATH = DOCS_DIR / "ASSET_INTELLIGENCE.yaml"
STORY_BEATS_PATH = DOCS_DIR / "STORY_BEATS.yaml"
DB_PATH = (
    REPO_ROOT.parent
    / "ai-agent-video-editor"
    / ".cut-notes"
    / "cut-notes.sqlite"
)

VO_SAFETY_MARGIN = 0.4
STILL_UNDER_VO_THRESHOLD = 6.0
LONG_VO_BLOCK_THRESHOLD = 20.0
ERROR_CODES = {
    "CHRONOLOGY_ERROR",
    "VO_CUTOFF_ERROR",
    "MISSING_TIMELINE_START_ERROR",
}


# ── Loaders ───────────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def _build_basename_to_intel() -> dict[str, dict]:
    ai = _load_yaml(ASSET_INTELLIGENCE_PATH)
    out: dict[str, dict] = {}
    for asset in ai.get("assets", []):
        fp = asset.get("file", "")
        if fp.startswith("synthetic://"):
            continue
        out[fp.split("/")[-1]] = asset
    return out


# ── Validators ────────────────────────────────────────────────────────


def _segment_beat(beats: list[dict], start: float, end: float) -> dict | None:
    for beat in beats:
        if beat["start"] <= start < beat["end"] and end <= beat["end"] + 1e-6:
            return beat
    return None


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if path else ""


def validate_chronology(
    active_visual: list[dict],
    beats: list[dict],
    basename_to_intel: dict[str, dict],
) -> list[dict]:
    issues = []
    for seg in active_visual:
        src = seg.get("source") or ""
        if not src:
            continue
        intel = basename_to_intel.get(_basename(src))
        if intel is None:
            issues.append(
                {
                    "code": "CHRONOLOGY_ERROR",
                    "clip_id": seg["clip_id"],
                    "window": seg["window"],
                    "message": (
                        f"source {_basename(src)} not in ASSET_INTELLIGENCE — "
                        "cannot validate chronology"
                    ),
                }
            )
            continue
        beat = _segment_beat(beats, float(seg["window"][0]), float(seg["window"][1]))
        if beat is None:
            continue
        if intel["story_phase"] not in beat["allowed_story_phases"]:
            issues.append(
                {
                    "code": "CHRONOLOGY_ERROR",
                    "clip_id": seg["clip_id"],
                    "window": seg["window"],
                    "message": (
                        f"clip phase '{intel['story_phase']}' not in beat "
                        f"'{beat['id']}' allowed phases "
                        f"{beat['allowed_story_phases']}"
                    ),
                }
            )
    return issues


def _voiceover_windows(clips: list[dict]) -> list[dict]:
    out = []
    for c in clips:
        if c.get("track") != "voiceover":
            continue
        tl = c.get("timeline", {})
        out.append(
            {
                "clip_id": c["id"],
                "start": float(tl.get("start", 0.0)),
                "end": float(tl.get("end", 0.0)),
                "file": _basename((c.get("source") or {}).get("file", "")),
            }
        )
    out.sort(key=lambda v: v["start"])
    return out


def _segments_in_window(
    active_visual: list[dict], start: float, end: float
) -> list[dict]:
    """Return active_visual segments that overlap [start, end)."""
    out = []
    for seg in active_visual:
        s, e = float(seg["window"][0]), float(seg["window"][1])
        if e <= start or s >= end:
            continue
        out.append(seg)
    return out


def validate_still_under_vo(
    active_visual: list[dict],
    voiceovers: list[dict],
    basename_to_intel: dict[str, dict],
) -> list[dict]:
    issues = []
    for vo in voiceovers:
        for seg in _segments_in_window(active_visual, vo["start"], vo["end"]):
            # is the segment a still?
            if seg.get("lane") != "still":
                # Also catch image assets surfaced via lanes other than 'still'
                src = seg.get("source") or ""
                intel = basename_to_intel.get(_basename(src))
                if not (intel and not intel.get("has_motion", True)):
                    continue
            # compute overlap duration
            s = max(vo["start"], float(seg["window"][0]))
            e = min(vo["end"], float(seg["window"][1]))
            overlap = e - s
            if overlap > STILL_UNDER_VO_THRESHOLD:
                issues.append(
                    {
                        "code": "STILL_UNDER_VO_WARNING",
                        "clip_id": seg["clip_id"],
                        "window": seg["window"],
                        "message": (
                            f"still active for {overlap:.1f}s under VO "
                            f"{vo['clip_id']} (threshold "
                            f"{STILL_UNDER_VO_THRESHOLD}s)"
                        ),
                    }
                )
    return issues


def validate_vo_cutoff(
    active_visual: list[dict],
    voiceovers: list[dict],
) -> list[dict]:
    issues = []
    for vo in voiceovers:
        # Total visual coverage of any visible segment within VO window
        coverage_end = vo["start"]
        for seg in _segments_in_window(active_visual, vo["start"], vo["end"] + 5.0):
            s, e = float(seg["window"][0]), float(seg["window"][1])
            if s <= coverage_end + 1e-3:
                coverage_end = max(coverage_end, e)
        coverage_seconds = coverage_end - vo["start"]
        required = (vo["end"] - vo["start"]) + VO_SAFETY_MARGIN
        if coverage_seconds + 1e-3 < required:
            issues.append(
                {
                    "code": "VO_CUTOFF_ERROR",
                    "clip_id": vo["clip_id"],
                    "window": [vo["start"], vo["end"]],
                    "message": (
                        f"visual coverage {coverage_seconds:.2f}s < required "
                        f"{required:.2f}s (vo duration "
                        f"{(vo['end']-vo['start']):.2f}s + "
                        f"{VO_SAFETY_MARGIN}s safety)"
                    ),
                }
            )
    return issues


def validate_dialogue_collision(
    active_visual: list[dict],
    voiceovers: list[dict],
    clips: list[dict],
    basename_to_intel: dict[str, dict],
) -> list[dict]:
    """Flag VO segments where dialogue-bearing a-roll is the active visual.

    Lane convention: only `a_roll` plays its source audio at render time.
    `ambient` / `b_roll` / `still` lanes are silent cover by design, so they
    do not collide. An explicit "silent"/"muted"/"ducked" tag in the clip
    notes also suppresses the warning.
    """
    notes_by_clip = {c["id"]: (c.get("notes") or "").lower() for c in clips}
    issues = []
    for vo in voiceovers:
        for seg in _segments_in_window(active_visual, vo["start"], vo["end"]):
            if seg.get("lane") != "a_roll":
                continue
            src = seg.get("source") or ""
            intel = basename_to_intel.get(_basename(src))
            if not intel or not intel.get("has_dialogue"):
                continue
            note = notes_by_clip.get(seg["clip_id"], "")
            if any(tag in note for tag in ("silent", "muted", "ducked", "no audio")):
                continue
            issues.append(
                {
                    "code": "DIALOGUE_COLLISION_WARNING",
                    "clip_id": seg["clip_id"],
                    "window": seg["window"],
                    "message": (
                        f"a-roll with dialogue active under VO {vo['clip_id']} "
                        "and clip notes do not declare source audio "
                        "muted/ducked/silent"
                    ),
                }
            )
    return issues


def validate_missing_timeline_start(pass_id: str) -> list[dict]:
    if not DB_PATH.exists():
        return [
            {
                "code": "MISSING_TIMELINE_START_ERROR",
                "clip_id": "",
                "window": None,
                "message": (
                    f"cannot check timelineStart: SQLite not found at {DB_PATH}"
                ),
            }
        ]
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, role, "order"
        FROM timeline_items
        WHERE projectId = 'piano-hand-size-part-2'
          AND passId = ?
          AND enabled = 1
          AND timelineStart IS NULL
        ORDER BY "order"
        """,
        (pass_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "code": "MISSING_TIMELINE_START_ERROR",
            "clip_id": r["id"],
            "window": None,
            "message": (
                f"enabled clip has NULL timelineStart "
                f"(role={r['role']}, order={r['order']}) — Step 13 fixes this"
            ),
        }
        for r in rows
    ]


def validate_long_vo_block(
    active_visual: list[dict],
    voiceovers: list[dict],
) -> list[dict]:
    """PACING_WARNING (item 5): >LONG_VO_BLOCK_THRESHOLD continuous VO+broll
    block with no a-roll burst, title card, or major visual change.

    Strategy: walk consecutive VOs; for each VO, check whether the active
    visual under it is exclusively b-roll/still/ambient and the VO duration
    itself exceeds the threshold. If so, also check whether the visual
    changes at least once mid-VO (>=2 segments). If only one segment covers
    the whole VO with no a-roll break, raise PACING_WARNING.
    """
    issues = []
    for vo in voiceovers:
        vo_dur = vo["end"] - vo["start"]
        if vo_dur <= LONG_VO_BLOCK_THRESHOLD:
            continue
        segs = _segments_in_window(active_visual, vo["start"], vo["end"])
        if not segs:
            continue
        a_roll_present = any(s.get("lane") == "a_roll" for s in segs)
        title_card_present = any(s.get("lane") == "title_card" for s in segs)
        if a_roll_present or title_card_present:
            continue
        if len(segs) < 2:
            issues.append(
                {
                    "code": "PACING_WARNING",
                    "clip_id": vo["clip_id"],
                    "window": [vo["start"], vo["end"]],
                    "message": (
                        f"VO runs {vo_dur:.1f}s with a single covering visual "
                        "and no a-roll burst, title card, or visual break"
                    ),
                }
            )
    return issues


# ── Driver ────────────────────────────────────────────────────────────


def run(pass_id: str) -> tuple[list[dict], Path]:
    pass_yaml = TIMELINES_DIR / f"{pass_id}.yaml"
    if not pass_yaml.exists():
        raise FileNotFoundError(f"pass yaml not found: {pass_yaml}")

    dump = _load_yaml(pass_yaml)
    beats_doc = _load_yaml(STORY_BEATS_PATH)
    basename_to_intel = _build_basename_to_intel()

    beats = beats_doc["beats"]
    clips = dump.get("clips", [])
    active_visual = dump.get("active_visual", [])
    voiceovers = _voiceover_windows(clips)

    issues: list[dict] = []
    issues.extend(validate_chronology(active_visual, beats, basename_to_intel))
    issues.extend(
        validate_still_under_vo(active_visual, voiceovers, basename_to_intel)
    )
    issues.extend(validate_vo_cutoff(active_visual, voiceovers))
    issues.extend(
        validate_dialogue_collision(
            active_visual, voiceovers, clips, basename_to_intel
        )
    )
    issues.extend(validate_missing_timeline_start(pass_id))
    issues.extend(validate_long_vo_block(active_visual, voiceovers))

    out_path = TIMELINES_DIR / f"{pass_id}-semantic-issues.yaml"
    summary = _summarise(issues)
    payload = {
        "pass_id": pass_id,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {
            "vo_safety_margin_seconds": VO_SAFETY_MARGIN,
            "still_under_vo_threshold_seconds": STILL_UNDER_VO_THRESHOLD,
            "long_vo_block_threshold_seconds": LONG_VO_BLOCK_THRESHOLD,
        },
        "summary": summary,
        "issues": issues,
    }
    with out_path.open("w") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, default_flow_style=None, width=100)

    return issues, out_path


def _summarise(issues: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    return {
        "total": len(issues),
        "by_code": dict(sorted(counts.items())),
        "errors": sum(1 for i in issues if i["code"] in ERROR_CODES),
        "warnings": sum(1 for i in issues if i["code"] not in ERROR_CODES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pass_id", help="Pass id (filename stem in timelines/)")
    args = parser.parse_args()

    try:
        issues, out_path = run(args.pass_id)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summary = _summarise(issues)
    print(f"wrote {out_path.relative_to(REPO_ROOT)}")
    print(
        f"  total={summary['total']}  errors={summary['errors']}  "
        f"warnings={summary['warnings']}"
    )
    for code, count in summary["by_code"].items():
        print(f"  {code}: {count}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
