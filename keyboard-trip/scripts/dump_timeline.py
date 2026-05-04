"""
Snapshot a pass's timeline state from the editor SQLite database into a
human-readable YAML file the AI can read before any editing pass.

This is the single source of truth that AI editing passes MUST consult.
Any clip whose ``last_edited_by`` is ``user`` is locked — the AI must not
modify its timing, source range, role, or rotation.

Workflow:

    python3 scripts/dump_timeline.py pass-9-real-vo-extended-montage

    1. Reads the live SQLite at ai-agent-video-editor/.cut-notes/.
    2. Generates contact sheets for any source clip in the pass that is
       missing one (so the AI has visual context for every clip).
    3. Writes timelines/<pass-id>.yaml with per-clip detail, an
       ``active_visual`` view of which clip is on top at each moment,
       and an ``issues`` block (overlaps, gaps, source overruns, audio
       collisions).

Pass ``--list`` to see available passes. Pass ``--all`` to dump every pass.
"""

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT.parent / "ai-agent-video-editor" / ".cut-notes" / "cut-notes.sqlite"
TIMELINES_DIR = ROOT / "timelines"
CONTACT_SHEETS_DIR = ROOT / "footage" / "91_Visual_Contact_Sheets"
CONTACT_SHEET_INTERVAL_S = 2

# Higher number = lower visual priority. Audio lanes are skipped entirely
# when computing the active visual track.
VISUAL_PRIORITY = {
    "a_roll": 0,
    "b_roll": 1,
    "still": 2,
    "title_card": 3,
    "placeholder": 4,
    "ambient": 5,
}
AUDIO_LANES = {"voiceover", "music"}
EXPECTED_AUDIO_PAIRS = {frozenset({"voiceover", "music"})}

# ── DB helpers ─────────────────────────────────────────────────────────────


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(f"SQLite not found: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_passes(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, status FROM passes ORDER BY \"order\""
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_clips(conn: sqlite3.Connection, pass_id: str) -> list[dict]:
    # Order matches the editor app's getTimelineItems query so the cursor
    # logic in resolve_timeline_starts produces identical positions.
    rows = conn.execute(
        """
        SELECT
          ti.id, ti.section, ti.role, ti.timelineStart, ti.sourceIn,
          ti.sourceOut, ti.targetDuration, ti.rotationOverride,
          ti.textOverlay, ti.notes, ti."order", ti.enabled,
          ti.lastEditedBy, ti.lastEditedAt,
          a.id AS assetId, a.kind AS assetKind, a.path AS assetPath,
          a.basename AS assetBasename, a.originalId AS assetOriginalId,
          a.durationSeconds AS assetDuration, a.rotation AS assetRotation,
          a.metadata AS assetMetadata
        FROM timeline_items ti
        LEFT JOIN assets a ON a.id = ti.assetId
        WHERE ti.projectId = 'piano-hand-size-part-2'
          AND ti.passId = ?
          AND ti.enabled = 1
        ORDER BY ti."order" ASC
        """,
        (pass_id,),
    ).fetchall()
    clips = [dict(r) for r in rows]
    resolve_timeline_starts(clips)
    return clips


# ── Geometry helpers ───────────────────────────────────────────────────────


def clip_duration(clip: dict) -> float:
    duration = clip.get("targetDuration")
    if duration is None:
        sin = clip.get("sourceIn") or 0.0
        sout = clip.get("sourceOut") or sin
        duration = max(0.0, sout - sin)
    return float(duration)


def clip_window(clip: dict) -> tuple[float, float]:
    """Window in seconds. Requires resolve_timeline_starts() to have run."""
    start = float(clip["_resolved_start"])
    return start, start + clip_duration(clip)


def resolve_timeline_starts(clips: list[dict]) -> None:
    """Mirror the editor app's getTimelineClips cursor logic: clips without
    an explicit timelineStart stack consecutively after the running cursor;
    explicit-timelineStart clips use their value but don't advance the cursor."""
    # Same iteration order as the SQL query — by timelineStart NULLS FIRST,
    # then by role. Items with explicit positions must come after the run of
    # null-position items they sit alongside, just like the editor's render.
    cursor = 0.0
    for clip in clips:
        if clip.get("timelineStart") is None:
            clip["_resolved_start"] = cursor
            cursor += clip_duration(clip)
        else:
            clip["_resolved_start"] = float(clip["timelineStart"])


def visual_clips(clips: list[dict]) -> list[dict]:
    return [c for c in clips if c["role"] in VISUAL_PRIORITY]


def audio_clips(clips: list[dict]) -> list[dict]:
    return [c for c in clips if c["role"] in AUDIO_LANES]


def build_active_visual(clips: list[dict]) -> list[dict]:
    """Project visual clips onto a single linear visible track.

    For every point on the master timeline, returns the clip that wins by
    lane priority. Returns a list of contiguous segments — `window` (start,
    end), `clip_id`, `lane`, `source` (relative path).
    """
    visuals = visual_clips(clips)
    if not visuals:
        return []
    # Sweep-line on edges
    edges: set[float] = {0.0}
    for clip in visuals:
        start, end = clip_window(clip)
        edges.add(start)
        edges.add(end)
    sorted_edges = sorted(edges)
    segments: list[dict] = []
    for i in range(len(sorted_edges) - 1):
        a, b = sorted_edges[i], sorted_edges[i + 1]
        if b - a < 1e-3:
            continue
        midpoint = (a + b) / 2
        candidates = [
            c for c in visuals
            if clip_window(c)[0] <= midpoint < clip_window(c)[1]
        ]
        if not candidates:
            continue
        winner = min(candidates, key=lambda c: VISUAL_PRIORITY[c["role"]])
        if segments and segments[-1]["clip_id"] == winner["id"]:
            segments[-1]["window"][1] = round(b, 3)
        else:
            segments.append({
                "window": [round(a, 3), round(b, 3)],
                "clip_id": winner["id"],
                "lane": winner["role"],
                "source": clip_relative_source(winner) or "",
            })
    return segments


def clip_relative_source(clip: dict) -> str | None:
    metadata = parse_metadata(clip.get("assetMetadata"))
    return metadata.get("relativePath") if isinstance(metadata, dict) else None


def parse_metadata(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


# ── Validation ─────────────────────────────────────────────────────────────


def validate(clips: list[dict], active_visual: list[dict]) -> dict:
    issues: dict = {
        "overlaps": [],
        "gaps": [],
        "audio_collisions": [],
        "source_overruns": [],
    }

    # Per-lane visual overlaps (two clips on a_roll at the same time, etc.)
    by_lane: dict[str, list[dict]] = {}
    for clip in visual_clips(clips):
        by_lane.setdefault(clip["role"], []).append(clip)
    for lane, lane_clips in by_lane.items():
        sorted_clips = sorted(lane_clips, key=lambda c: clip_window(c)[0])
        for i in range(len(sorted_clips) - 1):
            a_start, a_end = clip_window(sorted_clips[i])
            b_start, b_end = clip_window(sorted_clips[i + 1])
            if b_start < a_end - 1e-3:
                issues["overlaps"].append({
                    "lane": lane,
                    "clips": [sorted_clips[i]["id"], sorted_clips[i + 1]["id"]],
                    "window": [round(b_start, 3), round(min(a_end, b_end), 3)],
                    "delta": round(a_end - b_start, 3),
                })

    # Gaps in the active visual track (no clip showing).
    if active_visual:
        cursor = 0.0
        for seg in active_visual:
            if seg["window"][0] - cursor > 0.5:
                issues["gaps"].append({
                    "window": [round(cursor, 3), round(seg["window"][0], 3)],
                    "duration": round(seg["window"][0] - cursor, 3),
                })
            cursor = max(cursor, seg["window"][1])

    # Audio collisions — only flag combinations not in EXPECTED_AUDIO_PAIRS.
    audios = audio_clips(clips)
    for i, a in enumerate(audios):
        a_start, a_end = clip_window(a)
        for b in audios[i + 1:]:
            b_start, b_end = clip_window(b)
            overlap_start = max(a_start, b_start)
            overlap_end = min(a_end, b_end)
            if overlap_end - overlap_start <= 1e-3:
                continue
            pair = frozenset({a["role"], b["role"]})
            if pair in EXPECTED_AUDIO_PAIRS:
                continue  # voiceover + music ducked is the desired mix
            issues["audio_collisions"].append({
                "clips": [a["id"], b["id"]],
                "roles": sorted([a["role"], b["role"]]),
                "window": [round(overlap_start, 3), round(overlap_end, 3)],
            })

    # Source overruns: clip's source range exceeds the asset's true duration.
    for clip in clips:
        asset_dur = clip.get("assetDuration")
        sin = clip.get("sourceIn") or 0.0
        sout = clip.get("sourceOut") or sin + (clip.get("targetDuration") or 0.0)
        if asset_dur and sout > asset_dur + 0.5:
            issues["source_overruns"].append({
                "clip": clip["id"],
                "source_out": round(sout, 3),
                "asset_duration": round(asset_dur, 3),
                "overrun": round(sout - asset_dur, 3),
            })
    return issues


# ── Contact sheets ─────────────────────────────────────────────────────────


def ensure_contact_sheet(source_abs: Path, sheet_dir: Path) -> dict:
    """Return a status dict — generates sheets if missing or stale."""
    if not source_abs.exists():
        return {"status": "missing_source", "path": None, "sheets": 0}
    if not source_abs.is_file():
        return {"status": "not_a_file", "path": None, "sheets": 0}

    # Only video files get sheets. Audio/stills are skipped.
    if source_abs.suffix.lower() not in {".mov", ".mp4", ".m4v"}:
        return {"status": "skipped_non_video", "path": None, "sheets": 0}

    sheet_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(sheet_dir.glob("*.jpg"))
    source_mtime = source_abs.stat().st_mtime
    if existing:
        oldest_sheet = min(s.stat().st_mtime for s in existing)
        if oldest_sheet >= source_mtime:
            return {
                "status": "ok",
                "path": str(sheet_dir.relative_to(ROOT)),
                "sheets": len(existing),
            }
        # Stale — wipe and regenerate
        for s in existing:
            s.unlink()

    base = source_abs.stem
    pattern = sheet_dir / f"{base}_sheet_%03d.jpg"
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(source_abs),
        "-vf",
        f"fps=1/{CONTACT_SHEET_INTERVAL_S},scale=320:-1,"
        f"drawtext=fontcolor=white:fontsize=18:box=1:boxcolor=black@0.65:"
        f"text='%{{pts\\:hms}}':x=8:y=8,tile=5x6:padding=8:margin=8",
        str(pattern),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {
            "status": "ffmpeg_failed",
            "path": str(sheet_dir.relative_to(ROOT)),
            "sheets": 0,
            "error": result.stderr[-300:],
        }
    new_count = len(list(sheet_dir.glob("*.jpg")))
    return {
        "status": "generated",
        "path": str(sheet_dir.relative_to(ROOT)),
        "sheets": new_count,
    }


# ── Main dump ──────────────────────────────────────────────────────────────


def dump_pass(conn: sqlite3.Connection, pass_id: str, skip_sheets: bool) -> Path:
    pass_row = conn.execute(
        "SELECT id, name, status FROM passes WHERE id = ?", (pass_id,)
    ).fetchone()
    if not pass_row:
        sys.exit(f"Unknown pass: {pass_id}")

    clips = fetch_clips(conn, pass_id)
    active_visual = build_active_visual(clips)

    # Mark which clips are the "top visual" at any point (so reviewers can
    # see at a glance which clip is the active visual lane).
    top_visual_ids = {seg["clip_id"] for seg in active_visual}

    # Ensure a contact sheet for every unique source file referenced.
    sheet_status: dict[str, dict] = {}
    project_root = ROOT
    if not skip_sheets:
        unique_sources: dict[Path, Path] = {}
        for clip in clips:
            rel = clip_relative_source(clip)
            if not rel:
                continue
            source_abs = project_root / rel
            if source_abs in unique_sources:
                continue
            unique_sources[source_abs] = (
                CONTACT_SHEETS_DIR / source_abs.stem
            )
        print(f"[contact-sheets] {len(unique_sources)} unique sources")
        for source_abs, sheet_dir in unique_sources.items():
            status = ensure_contact_sheet(source_abs, sheet_dir)
            sheet_status[str(source_abs.relative_to(project_root))] = status
            if status["status"] == "generated":
                print(f"  generated {source_abs.name} -> {status['sheets']} sheets")

    issues = validate(clips, active_visual)

    summary = {
        "clips": len(clips),
        "locked_by_user": sum(
            1 for c in clips if (c.get("lastEditedBy") or "").lower() == "user"
        ),
        "total_duration_seconds": round(
            max((clip_window(c)[1] for c in clips), default=0.0), 3
        ),
        "active_visual_segments": len(active_visual),
        "issues": {k: len(v) for k, v in issues.items()},
    }

    document = {
        "project": "piano-hand-size-part-2",
        "pass": {
            "id": pass_row["id"],
            "name": pass_row["name"],
            "status": pass_row["status"],
        },
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "active_visual": active_visual,
        "clips": [
            serialize_clip(c, is_top=(c["id"] in top_visual_ids), sheet_status=sheet_status)
            for c in clips
        ],
        "issues": issues,
    }

    TIMELINES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TIMELINES_DIR / f"{pass_id}.yaml"
    with out_path.open("w") as fh:
        fh.write(
            "# Auto-generated by scripts/dump_timeline.py.\n"
            "# Source of truth for AI editing passes. Clips with\n"
            "# last_edited_by: user are locked — do not modify their\n"
            "# timeline, source range, role, or rotation.\n\n"
        )
        yaml.safe_dump(document, fh, sort_keys=False, default_flow_style=False, width=100)

    print(f"[dump] wrote {out_path.relative_to(ROOT.parent)}")
    print_summary(summary, issues)
    return out_path


def serialize_clip(clip: dict, is_top: bool, sheet_status: dict) -> dict:
    start, end = clip_window(clip)
    rel_source = clip_relative_source(clip)
    sheet_info = sheet_status.get(rel_source) if rel_source else None
    return {
        "id": clip["id"],
        "section": clip["section"],
        "track": clip["role"],
        "is_top_visual": bool(is_top),
        "timeline": {
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
        },
        "source": {
            "file": rel_source,
            "in": round(clip.get("sourceIn") or 0.0, 3) if clip.get("sourceIn") is not None else None,
            "out": round(clip.get("sourceOut") or 0.0, 3) if clip.get("sourceOut") is not None else None,
            "asset_duration": (
                round(clip["assetDuration"], 3) if clip.get("assetDuration") else None
            ),
        },
        "rotation": clip.get("rotationOverride") or clip.get("assetRotation") or 0,
        "text_overlay": clip.get("textOverlay"),
        "last_edited_by": clip.get("lastEditedBy") or "ai",
        "last_edited_at": clip.get("lastEditedAt"),
        "contact_sheet": sheet_info or {"status": "n/a"},
        "notes": clip.get("notes"),
    }


def print_summary(summary: dict, issues: dict) -> None:
    print(
        f"[summary] {summary['clips']} clips · "
        f"{summary['locked_by_user']} locked-by-user · "
        f"{summary['total_duration_seconds']:.1f}s total"
    )
    flat = sum(len(v) for v in issues.values())
    if flat:
        print(f"[issues] {flat} issue(s):")
        for kind, items in issues.items():
            if items:
                print(f"  {kind}: {len(items)}")
                for item in items[:5]:
                    print(f"    - {item}")
                if len(items) > 5:
                    print(f"    ... and {len(items) - 5} more")
    else:
        print("[issues] none")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pass_id", nargs="?", help="Pass ID to dump")
    parser.add_argument("--list", action="store_true", help="List available passes")
    parser.add_argument("--all", action="store_true", help="Dump every pass")
    parser.add_argument(
        "--skip-contact-sheets",
        action="store_true",
        help="Skip contact-sheet generation (faster, riskier for AI plans)",
    )
    args = parser.parse_args()

    conn = open_db()
    if args.list:
        for p in list_passes(conn):
            print(f"  {p['status']:<14} {p['id']}  ({p['name']})")
        return

    if not shutil.which("ffmpeg"):
        sys.stderr.write(
            "warning: ffmpeg not found on PATH — contact sheets cannot be regenerated\n"
        )

    if args.all:
        for p in list_passes(conn):
            print(f"\n=== {p['name']} ({p['id']}) ===")
            dump_pass(conn, p["id"], args.skip_contact_sheets)
        return

    if not args.pass_id:
        parser.error("Pass ID required (or use --list / --all)")
    dump_pass(conn, args.pass_id, args.skip_contact_sheets)


if __name__ == "__main__":
    main()
