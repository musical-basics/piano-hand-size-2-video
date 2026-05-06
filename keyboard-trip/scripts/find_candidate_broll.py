#!/usr/bin/env python3
"""Find candidate b-roll ranges that match a query.

Implements Plan Step 21 / Checklist item 20.

Reads ASSET_INTELLIGENCE.yaml's `best_ranges` for assets matching the
query (story_phase / clip_type / minimum duration), excludes ranges
already used in the current pass, and prints a ranked list with
asset, [in,out], score, reason.

Usage:
  python3 scripts/find_candidate_broll.py
      --story-phase drive_to_titusville
      --clip-type driving_broll
      --min-duration 4
      [--exclude-used-from <pass-id>]   # default: latest pass
      [--limit N]                       # default: 20

Score (0-1): score = 0.5 * (range_duration / target_duration capped 1.0)
                   + 0.3 * has_motion bonus
                   + 0.2 * specificity bonus (story_phase + clip_type
                                              both matched).
Higher = better fit. Tie-break by trip_order (earlier = preferred).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSET_INTELLIGENCE_PATH = REPO_ROOT / "docs" / "ASSET_INTELLIGENCE.yaml"
TIMELINES_DIR = REPO_ROOT / "timelines"


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def _latest_pass_yaml() -> Path | None:
    import re
    candidates = list(TIMELINES_DIR.glob("pass-*-*.yaml"))
    candidates = [
        p for p in candidates
        if not p.name.endswith("-ai-brief.yaml")
        and not p.name.endswith("-semantic-issues.yaml")
    ]

    def pass_num(p: Path) -> int:
        m = re.match(r"pass-(\d+)-", p.name)
        return int(m.group(1)) if m else -1

    candidates.sort(key=pass_num)
    return candidates[-1] if candidates else None


def _used_ranges(pass_yaml: Path) -> dict[str, list[tuple[float, float]]]:
    """Return basename → [(in, out), ...] for clips that already use
    each source asset in the named pass."""
    if not pass_yaml.exists():
        return {}
    dump = _load_yaml(pass_yaml)
    used: dict[str, list[tuple[float, float]]] = {}
    for clip in dump.get("clips", []):
        src = (clip.get("source") or {}).get("file") or ""
        if not src:
            continue
        bn = src.split("/")[-1]
        sin = float((clip["source"].get("in") or 0.0))
        sout = float((clip["source"].get("out") or 0.0))
        if sout <= sin:
            sout = sin + float(clip.get("timeline", {}).get("duration", 0.0))
        used.setdefault(bn, []).append((sin, sout))
    return used


def _range_substantially_used(
    candidate: tuple[float, float], used_for_basename: list[tuple[float, float]]
) -> bool:
    """Exclude only when the used windows cover >70% of the candidate
    range (avoids dropping a 30s best_range just because 4s was used)."""
    cs, ce = candidate
    cdur = max(0.0, ce - cs)
    if cdur <= 0:
        return True
    overlap_total = 0.0
    for us, ue in used_for_basename:
        s = max(cs, us)
        e = min(ce, ue)
        if e > s:
            overlap_total += e - s
    return (overlap_total / cdur) > 0.7


def find_candidates(
    story_phase: str | None,
    clip_type: str | None,
    min_duration: float,
    exclude_used_from: Path | None,
    limit: int,
) -> list[dict]:
    ai = _load_yaml(ASSET_INTELLIGENCE_PATH)
    used = _used_ranges(exclude_used_from) if exclude_used_from else {}

    candidates = []
    for asset in ai.get("assets", []):
        # Match filters
        sp_match = (story_phase is None) or (asset.get("story_phase") == story_phase)
        ct_match = (clip_type is None) or (asset.get("clip_type") == clip_type)
        if not (sp_match and ct_match):
            continue
        bn = asset["file"].split("/")[-1]
        used_for_this = used.get(bn, [])
        for r in asset.get("best_ranges", []) or []:
            in_s = float(r["in"])
            out_s = float(r["out"])
            dur = out_s - in_s
            if dur < min_duration:
                continue
            if used_for_this and _range_substantially_used((in_s, out_s), used_for_this):
                continue
            # Score
            duration_fit = min(1.0, dur / max(min_duration, 0.001))
            motion = 0.3 if asset.get("has_motion") else 0.0
            specificity = (
                0.2 if (story_phase and clip_type and sp_match and ct_match) else 0.05
            )
            score = round(0.5 * duration_fit + motion + specificity, 3)
            candidates.append(
                {
                    "asset_id": asset["asset_id"],
                    "file": asset["file"],
                    "story_phase": asset["story_phase"],
                    "clip_type": asset["clip_type"],
                    "trip_order": asset.get("trip_order", 0),
                    "range": [in_s, out_s],
                    "duration": round(dur, 2),
                    "score": score,
                    "reason": r.get("reason", ""),
                }
            )

    candidates.sort(key=lambda c: (-c["score"], c["trip_order"]))
    return candidates[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--story-phase")
    parser.add_argument("--clip-type")
    parser.add_argument("--min-duration", type=float, default=2.0)
    parser.add_argument(
        "--exclude-used-from",
        help="Pass id whose used ranges to exclude (default: latest)",
    )
    parser.add_argument(
        "--no-exclude-used", action="store_true",
        help="Disable used-range exclusion entirely",
    )
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if args.no_exclude_used:
        exclude = None
    elif args.exclude_used_from:
        exclude = TIMELINES_DIR / f"{args.exclude_used_from}.yaml"
    else:
        exclude = _latest_pass_yaml()

    if exclude:
        print(f"# excluding ranges already used in {exclude.name}")

    candidates = find_candidates(
        args.story_phase, args.clip_type, args.min_duration, exclude, args.limit
    )

    if not candidates:
        print("no candidates found", file=sys.stderr)
        return 1

    print(f"# {len(candidates)} candidates (sorted by score, then trip_order)")
    print()
    print(f"{'score':>6} {'phase':>22} {'type':>16} {'in':>6} {'out':>6} {'dur':>5}  asset")
    print("-" * 110)
    for c in candidates:
        print(
            f"{c['score']:>6.3f} {c['story_phase']:>22} {c['clip_type']:>16} "
            f"{c['range'][0]:>6.1f} {c['range'][1]:>6.1f} {c['duration']:>5.1f}  "
            f"{c['asset_id']}"
        )
        if c["reason"]:
            print(f"       └─ {c['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
