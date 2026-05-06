#!/usr/bin/env python3
"""Apply an edit_patch_plan.json to the SQLite source of truth.

Implements Plan Steps 24 + 25 + 26 (Checklist item 10).

Usage:
  python3 scripts/apply_timeline_patch.py <patch.json> [--dry-run]

Behavior:
  - Validates the patch against docs/edit_patch_plan.schema.json
  - Runs ALL pre-apply gates for ALL operations BEFORE any writes
    (source-overrun, target-exists, beat-chronology, lock-protection,
    explicit-timelineStart-on-insert, no-new-overlaps)
  - On --dry-run: prints the gate report and the would-write summary,
    no rows touched
  - On real run: opens a single transaction, applies all ops, stamps
    lastEditedBy='ai' + lastEditedAt=now on every touched row, commits
    once. Any error → rollback, no partial application.

Audio ops (set_volume, mute_source_audio, duck_music) are recorded in
the row's notes field with a structured `[audio: ...]` prefix until
item 18's render_from_timeline.py adds first-class audio columns.

Exit codes:
  0  applied (or dry-run passed)
  1  one or more gates failed
  2  invocation problem (file missing, JSON invalid, etc.)
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml

try:
    import jsonschema
except ImportError:
    print(
        "error: jsonschema not installed. Run: pip3 install --user jsonschema",
        file=sys.stderr,
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SCHEMA_PATH = DOCS_DIR / "edit_patch_plan.schema.json"
ASSET_INTELLIGENCE_PATH = DOCS_DIR / "ASSET_INTELLIGENCE.yaml"
STORY_BEATS_PATH = DOCS_DIR / "STORY_BEATS.yaml"
DB_PATH = (
    REPO_ROOT.parent
    / "ai-agent-video-editor"
    / ".cut-notes"
    / "cut-notes.sqlite"
)
PROJECT_ID = "piano-hand-size-part-2"


# ── State helpers ────────────────────────────────────────────────────


def _now_iso() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def _load_assets_index(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT id, basename, durationSeconds, path FROM assets"
    ).fetchall()
    return {
        r["id"]: {
            "id": r["id"],
            "basename": r["basename"],
            "duration": r["durationSeconds"],
            "path": r["path"],
        }
        for r in rows
    }


def _load_basename_to_phase() -> dict[str, str]:
    ai = _load_yaml(ASSET_INTELLIGENCE_PATH)
    out = {}
    for a in ai.get("assets", []):
        fp = a.get("file", "")
        if fp.startswith("synthetic://"):
            continue
        out[fp.split("/")[-1]] = a["story_phase"]
    return out


def _load_assetid_to_phase() -> dict[str, str]:
    """Map asset_id → story_phase (for insert/replace where we're handed
    the target asset id, not the basename)."""
    ai = _load_yaml(ASSET_INTELLIGENCE_PATH)
    out = {}
    for a in ai.get("assets", []):
        out[a["asset_id"]] = a["story_phase"]
    return out


def _load_clips(conn: sqlite3.Connection, pass_id: str) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT id, passId, section, role, "order", sourceIn, sourceOut,
               targetDuration, assetId, timelineStart, enabled,
               lastEditedBy, lastEditedAt, notes, rotationOverride, textOverlay
        FROM timeline_items
        WHERE projectId = ? AND passId = ?
        """,
        (PROJECT_ID, pass_id),
    ).fetchall()
    return {r["id"]: dict(r) for r in rows}


def _segment_beat(beats: list[dict], start: float, end: float) -> dict | None:
    for b in beats:
        if b["start"] <= start < b["end"] and end <= b["end"] + 1e-6:
            return b
    return None


def _clip_window(clip: dict) -> tuple[float, float]:
    start = clip.get("timelineStart")
    if start is None:
        # cursor-resolved clips have no real position; treat as 0-length
        return (0.0, 0.0)
    duration = clip.get("targetDuration")
    if duration is None:
        sin = clip.get("sourceIn") or 0.0
        sout = clip.get("sourceOut") or sin
        duration = max(0.0, sout - sin)
    return (float(start), float(start) + float(duration))


# ── Gates ────────────────────────────────────────────────────────────


class GateFailure(Exception):
    def __init__(self, op_index: int, code: str, message: str):
        super().__init__(f"op[{op_index}] {code}: {message}")
        self.op_index = op_index
        self.code = code
        self.message = message


def _check_lock(op_index: int, op: dict, clip: dict) -> None:
    if clip.get("lastEditedBy") == "user" and not op.get("unlock"):
        raise GateFailure(
            op_index,
            "LOCKED",
            f"clip {clip['id']} is lastEditedBy=user; add 'unlock': true to override",
        )


def _ffprobe_duration(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(out.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def _resolve_asset_duration(asset: dict) -> float | None:
    if asset.get("duration") is not None:
        return float(asset["duration"])
    rel = asset.get("path") or ""
    if not rel:
        return None
    candidate = REPO_ROOT.parent / rel
    if not candidate.exists():
        candidate = REPO_ROOT / rel
    dur = _ffprobe_duration(candidate)
    if dur is not None:
        asset["duration"] = dur  # cache so we don't probe twice
    return dur


def _check_source_overrun(
    op_index: int, asset: dict | None, source_out: float | None
) -> None:
    if source_out is None or asset is None:
        return
    duration = _resolve_asset_duration(asset)
    if duration is None:
        return
    if float(source_out) > duration + 1e-3:
        raise GateFailure(
            op_index,
            "SOURCE_OVERRUN",
            f"source_out {source_out} > asset duration {duration}",
        )


def _check_chronology(
    op_index: int,
    beats: list[dict],
    assetid_to_phase: dict[str, str],
    asset_id: str,
    timeline_start: float,
    duration: float,
) -> None:
    phase = assetid_to_phase.get(asset_id)
    if phase is None:
        # Unknown asset; let the validator surface this later as a warning.
        return
    end = timeline_start + duration
    beat = _segment_beat(beats, timeline_start, end)
    if beat is None:
        # Outside any beat (post-runtime); not a hard chronology error.
        return
    if phase not in beat["allowed_story_phases"]:
        raise GateFailure(
            op_index,
            "CHRONOLOGY",
            (
                f"asset story_phase '{phase}' not in beat '{beat['id']}' "
                f"allowed phases {beat['allowed_story_phases']}"
            ),
        )


def _check_no_new_overlap(
    op_index: int,
    state: dict[str, dict],
    clip_id: str,
    role: str,
    start: float,
    end: float,
) -> None:
    """Visual-lane overlap detection. Two enabled clips on the same
    role/lane must not occupy overlapping windows."""
    for other in state.values():
        if other["id"] == clip_id or not other.get("enabled"):
            continue
        if other.get("role") != role:
            continue
        os_, oe = _clip_window(other)
        if oe <= start + 1e-3 or os_ >= end - 1e-3:
            continue
        raise GateFailure(
            op_index,
            "OVERLAP",
            f"would overlap {other['id']} on lane {role} window [{os_},{oe}]",
        )


# ── Operation appliers ──────────────────────────────────────────────


def _apply_audio_note(notes: str | None, prefix: str) -> str:
    """Stamp a structured `[audio: ...]` line at the top of notes,
    replacing any existing `[audio: ...]` line."""
    notes = notes or ""
    cleaned = "\n".join(
        line for line in notes.splitlines() if not line.startswith("[audio:")
    )
    return (prefix + ("\n" + cleaned if cleaned.strip() else "")).strip()


# ── Driver ───────────────────────────────────────────────────────────


@dataclasses.dataclass
class Context:
    sim: dict[str, dict]
    assets: dict[str, dict]
    assetid_to_phase: dict[str, str]
    beats: list[dict]
    writes: list[tuple[str, tuple]]
    summary: list[str]
    pass_id: str


def run(patch_path: Path, dry_run: bool) -> int:
    if not patch_path.exists():
        print(f"error: patch not found: {patch_path}", file=sys.stderr)
        return 2
    try:
        with patch_path.open() as fh:
            patch = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"error: patch is not valid JSON: {exc}", file=sys.stderr)
        return 2

    schema = json.loads(SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(patch, schema)
    except jsonschema.ValidationError as exc:
        print(f"error: patch fails schema: {exc.message}", file=sys.stderr)
        return 2

    if not DB_PATH.exists():
        print(f"error: SQLite not found at {DB_PATH}", file=sys.stderr)
        return 2

    pass_id = patch["pass_id"]
    operations = patch["operations"]

    mode = "ro" if dry_run else "rwc"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row

    # Verify pass exists
    if not conn.execute(
        "SELECT 1 FROM passes WHERE id = ?", (pass_id,)
    ).fetchone():
        print(f"error: pass not found: {pass_id}", file=sys.stderr)
        conn.close()
        return 2

    assets = _load_assets_index(conn)
    state = _load_clips(conn, pass_id)
    # Empty passes: seed sim with a dummy row so handlers can read passId.
    if not state:
        state["__sentinel__"] = {"id": "__sentinel__", "passId": pass_id, "enabled": 0}
    beats = _load_yaml(STORY_BEATS_PATH)["beats"]
    assetid_to_phase = _load_assetid_to_phase()

    # Run gates against an in-memory copy of state, simulating each op so
    # later-op gates see the post-prior-ops state.
    sim_state: dict[str, dict] = {k: dict(v) for k, v in state.items()}
    ctx = Context(
        sim=sim_state,
        assets=assets,
        assetid_to_phase=assetid_to_phase,
        beats=beats,
        writes=[],
        summary=[],
        pass_id=pass_id,
    )

    try:
        for i, op in enumerate(operations):
            op_type = op["type"]
            handler = OP_HANDLERS.get(op_type)
            if handler is None:
                raise GateFailure(i, "UNKNOWN_OP", f"unknown op type: {op_type}")
            handler(i, op, ctx)
    except GateFailure as exc:
        print(f"GATE FAILED: {exc}", file=sys.stderr)
        conn.close()
        return 1

    print(f"intent: {patch['intent']}")
    print(f"pass:   {pass_id}")
    print(f"ops:    {len(operations)}  (gates passed)")
    for line in ctx.summary:
        print(" ", line)

    if dry_run:
        print(f"\ndry-run: {len(ctx.writes)} SQL statements would execute")
        conn.close()
        return 0

    try:
        conn.execute("BEGIN")
        for sql, params in ctx.writes:
            conn.execute(sql, params)
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"SQL error: {exc}", file=sys.stderr)
        conn.close()
        return 1
    conn.close()
    print(f"\napplied: {len(ctx.writes)} statements committed")
    return 0


# ── Per-op handlers ─────────────────────────────────────────────────


def _next_order(state: dict[str, dict]) -> int:
    return max((c.get("order") or 0) for c in state.values()) + 1 if state else 1


def _h_insert(i, op, ctx):
    clip = op["clip"]
    asset = ctx.assets.get(clip["asset_id"])
    if asset is None:
        raise GateFailure(i, "BAD_ASSET", f"asset {clip['asset_id']} not in DB")
    if "source_out" in clip:
        _check_source_overrun(i, asset, clip["source_out"])
    if clip["id"] in ctx.sim:
        raise GateFailure(i, "DUP_ID", f"clip id already exists: {clip['id']}")
    duration = clip.get("target_duration")
    if duration is None:
        duration = (clip.get("source_out") or 0) - (clip.get("source_in") or 0)
    duration = float(duration)
    start = float(clip["timeline_start"])
    _check_chronology(i, ctx.beats, ctx.assetid_to_phase, clip["asset_id"], start, duration)
    _check_no_new_overlap(i, ctx.sim, clip["id"], clip["role"], start, start + duration)

    ctx.sim[clip["id"]] = {
        "id": clip["id"],
        "section": clip["section"],
        "role": clip["role"],
        "order": _next_order(ctx.sim),
        "sourceIn": clip.get("source_in"),
        "sourceOut": clip.get("source_out"),
        "targetDuration": duration,
        "assetId": clip["asset_id"],
        "timelineStart": start,
        "enabled": 1,
        "lastEditedBy": "ai",
        "lastEditedAt": _now_iso(),
        "notes": clip.get("notes"),
        "rotationOverride": clip.get("rotation_override"),
        "textOverlay": clip.get("text_overlay"),
    }
    ctx.writes.append(
        (
            """
            INSERT INTO timeline_items (
                id, projectId, assetId, passId, section, "order",
                sourceIn, sourceOut, targetDuration, role, enabled,
                rotationOverride, textOverlay, notes, timelineStart,
                lastEditedBy, lastEditedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clip["id"],
                PROJECT_ID,
                clip["asset_id"],
                op.get("_pass_id_override") or sim_first_pass_id(ctx.sim),
                clip["section"],
                ctx.sim[clip["id"]]["order"],
                clip.get("source_in"),
                clip.get("source_out"),
                duration,
                clip["role"],
                1,
                clip.get("rotation_override"),
                clip.get("text_overlay"),
                clip.get("notes"),
                start,
                "ai",
                _now_iso(),
            ),
        )
    )
    ctx.summary.append(f"insert  {clip['id']:42s} @ {start:7.2f}s  ({duration:.2f}s) {clip['role']}")


def _h_disable(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    _check_lock(i, op, ctx.sim[clip_id])
    ctx.sim[clip_id]["enabled"] = 0
    ctx.writes.append(
        (
            "UPDATE timeline_items SET enabled = 0, lastEditedBy = ?, lastEditedAt = ? WHERE id = ?",
            ("ai", _now_iso(), clip_id),
        )
    )
    ctx.summary.append(f"disable {clip_id}")


def _h_move(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    clip = ctx.sim[clip_id]
    _check_lock(i, op, clip)
    new_start = float(op["timeline_start"])
    new_section = op.get("section", clip["section"])
    duration = clip.get("targetDuration") or 0.0
    if clip.get("assetId"):
        _check_chronology(
            i, ctx.beats, ctx.assetid_to_phase, clip["assetId"], new_start, duration
        )
    _check_no_new_overlap(
        i, ctx.sim, clip_id, clip["role"], new_start, new_start + duration
    )
    clip["timelineStart"] = new_start
    clip["section"] = new_section
    ctx.writes.append(
        (
            """UPDATE timeline_items SET timelineStart = ?, section = ?,
               lastEditedBy = ?, lastEditedAt = ? WHERE id = ?""",
            (new_start, new_section, "ai", _now_iso(), clip_id),
        )
    )
    ctx.summary.append(f"move    {clip_id:42s} → @ {new_start:.2f}s")


def _h_trim(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    clip = ctx.sim[clip_id]
    _check_lock(i, op, clip)
    new_in = op.get("source_in", clip.get("sourceIn"))
    new_out = op.get("source_out", clip.get("sourceOut"))
    new_dur = op.get("target_duration", clip.get("targetDuration"))
    asset = ctx.assets.get(clip.get("assetId"))
    _check_source_overrun(i, asset, new_out)
    if new_dur is None and new_out is not None and new_in is not None:
        new_dur = float(new_out) - float(new_in)
    clip["sourceIn"] = new_in
    clip["sourceOut"] = new_out
    clip["targetDuration"] = new_dur
    ctx.writes.append(
        (
            """UPDATE timeline_items SET sourceIn = ?, sourceOut = ?,
               targetDuration = ?, lastEditedBy = ?, lastEditedAt = ?
               WHERE id = ?""",
            (new_in, new_out, new_dur, "ai", _now_iso(), clip_id),
        )
    )
    ctx.summary.append(
        f"trim    {clip_id:42s} in={new_in} out={new_out} dur={new_dur}"
    )


def _h_replace(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    clip = ctx.sim[clip_id]
    _check_lock(i, op, clip)
    asset_id = op["asset_id"]
    asset = ctx.assets.get(asset_id)
    if asset is None:
        raise GateFailure(i, "BAD_ASSET", f"asset {asset_id} not in DB")
    new_in = op.get("source_in", clip.get("sourceIn"))
    new_out = op.get("source_out", clip.get("sourceOut"))
    _check_source_overrun(i, asset, new_out)
    duration = clip.get("targetDuration") or 0.0
    start = clip.get("timelineStart") or 0.0
    _check_chronology(i, ctx.beats, ctx.assetid_to_phase, asset_id, start, duration)
    clip["assetId"] = asset_id
    clip["sourceIn"] = new_in
    clip["sourceOut"] = new_out
    ctx.writes.append(
        (
            """UPDATE timeline_items SET assetId = ?, sourceIn = ?,
               sourceOut = ?, lastEditedBy = ?, lastEditedAt = ?
               WHERE id = ?""",
            (asset_id, new_in, new_out, "ai", _now_iso(), clip_id),
        )
    )
    ctx.summary.append(f"replace {clip_id:42s} → asset {asset_id}")


def _h_split(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    clip = ctx.sim[clip_id]
    _check_lock(i, op, clip)
    a_id = op["new_ids"]["a"]
    b_id = op["new_ids"]["b"]
    if a_id in ctx.sim or b_id in ctx.sim:
        raise GateFailure(i, "DUP_ID", f"new id already exists: {a_id} or {b_id}")
    split_at = float(op["split_at_source_seconds"])
    sin = float(clip.get("sourceIn") or 0.0)
    sout = float(clip.get("sourceOut") or 0.0)
    if not (sin < sin + split_at < sout):
        raise GateFailure(
            i, "BAD_SPLIT", f"split point {split_at}s outside source range [{sin},{sout}]"
        )
    start = float(clip.get("timelineStart") or 0.0)
    a_dur = split_at
    b_dur = (sout - sin) - split_at
    # Mark old as disabled, insert two new
    ctx.sim[clip_id]["enabled"] = 0
    ctx.sim[a_id] = {**clip, "id": a_id, "sourceOut": sin + split_at,
                 "targetDuration": a_dur, "timelineStart": start,
                 "enabled": 1, "order": _next_order(ctx.sim),
                 "lastEditedBy": "ai", "lastEditedAt": _now_iso()}
    ctx.sim[b_id] = {**clip, "id": b_id, "sourceIn": sin + split_at,
                 "targetDuration": b_dur, "timelineStart": start + a_dur,
                 "enabled": 1, "order": _next_order(ctx.sim),
                 "lastEditedBy": "ai", "lastEditedAt": _now_iso()}
    ctx.writes.append(
        (
            "UPDATE timeline_items SET enabled = 0, lastEditedBy = ?, lastEditedAt = ? WHERE id = ?",
            ("ai", _now_iso(), clip_id),
        )
    )
    for new_id, sin_v, sout_v, dur, ts in [
        (a_id, sin, sin + split_at, a_dur, start),
        (b_id, sin + split_at, sout, b_dur, start + a_dur),
    ]:
        ctx.writes.append(
            (
                """INSERT INTO timeline_items (
                    id, projectId, assetId, passId, section, "order",
                    sourceIn, sourceOut, targetDuration, role, enabled,
                    rotationOverride, textOverlay, notes, timelineStart,
                    lastEditedBy, lastEditedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_id,
                    PROJECT_ID,
                    clip.get("assetId"),
                    sim_first_pass_id(ctx.sim),
                    clip.get("section"),
                    ctx.sim[new_id]["order"],
                    sin_v,
                    sout_v,
                    dur,
                    clip.get("role"),
                    1,
                    clip.get("rotationOverride"),
                    clip.get("textOverlay"),
                    f"Split from {clip_id}",
                    ts,
                    "ai",
                    _now_iso(),
                ),
            )
        )
    ctx.summary.append(f"split   {clip_id} → {a_id} + {b_id} (at +{split_at}s)")


def _h_set_volume(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    clip = ctx.sim[clip_id]
    _check_lock(i, op, clip)
    note_line = f"[audio: volume={op['volume']}]"
    new_notes = _apply_audio_note(clip.get("notes"), note_line)
    clip["notes"] = new_notes
    ctx.writes.append(
        (
            "UPDATE timeline_items SET notes = ?, lastEditedBy = ?, lastEditedAt = ? WHERE id = ?",
            (new_notes, "ai", _now_iso(), clip_id),
        )
    )
    ctx.summary.append(f"volume  {clip_id:42s} = {op['volume']}")


def _h_mute(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    clip = ctx.sim[clip_id]
    _check_lock(i, op, clip)
    new_notes = _apply_audio_note(clip.get("notes"), "[audio: muted]")
    clip["notes"] = new_notes
    ctx.writes.append(
        (
            "UPDATE timeline_items SET notes = ?, lastEditedBy = ?, lastEditedAt = ? WHERE id = ?",
            (new_notes, "ai", _now_iso(), clip_id),
        )
    )
    ctx.summary.append(f"mute    {clip_id}")


def _h_duck(i, op, ctx):
    clip_id = op["clip_id"]
    if clip_id not in ctx.sim:
        raise GateFailure(i, "BAD_TARGET", f"clip not found: {clip_id}")
    clip = ctx.sim[clip_id]
    _check_lock(i, op, clip)
    s, e = op["duck_window"]
    note_line = f"[audio: duck volume={op['volume']} window=[{s},{e}]]"
    new_notes = _apply_audio_note(clip.get("notes"), note_line)
    clip["notes"] = new_notes
    ctx.writes.append(
        (
            "UPDATE timeline_items SET notes = ?, lastEditedBy = ?, lastEditedAt = ? WHERE id = ?",
            (new_notes, "ai", _now_iso(), clip_id),
        )
    )
    ctx.summary.append(
        f"duck    {clip_id:42s} = {op['volume']} over [{s}, {e}]"
    )


OP_HANDLERS = {
    "insert_clip": _h_insert,
    "disable_clip": _h_disable,
    "move_clip": _h_move,
    "trim_clip": _h_trim,
    "replace_visual": _h_replace,
    "split_clip": _h_split,
    "set_volume": _h_set_volume,
    "mute_source_audio": _h_mute,
    "duck_music": _h_duck,
}


def sim_first_pass_id(sim: dict[str, dict]) -> str | None:
    """Return any pass id from an existing sim row.

    Used so inserted rows inherit the patch's pass id without us having
    to re-thread it through every handler. The caller has already
    validated that the patch's pass_id matches the loaded state.
    """
    for c in sim.values():
        if "passId" in c and c["passId"]:
            return c["passId"]
    return None


# Ensure passId is loaded for inherit-on-insert
def _ensure_pass_id_in_state(state: dict[str, dict], pass_id: str) -> None:
    for c in state.values():
        c["passId"] = pass_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("patch", help="Path to edit_patch_plan.json")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate gates without writing"
    )
    args = parser.parse_args()
    return run(Path(args.patch), args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
