#!/usr/bin/env python3
"""Replace cursor-resolved timeline starts with explicit values.

Implements Plan Step 19 / Checklist item 13.

The editor's `getTimelineClips` and `dump_timeline.py`'s
`resolve_timeline_starts` both reconstruct positions for clips with
NULL `timelineStart` by stacking them after the running cursor. This
script writes those resolved positions back into SQLite as explicit
values so:

  - `validate_timeline_semantics.py` can flip
    `MISSING_TIMELINE_START_ERROR` from "documented baseline" to
    "must-fix regression" (Item 14).
  - `apply_timeline_patch.py`'s gates can rely on explicit positions.
  - The editor and renderer never disagree about where a clip starts.

Usage:
  python3 scripts/fill_explicit_timeline_starts.py <pass-id> [--dry-run]

Done-when (Item 13): re-dump after running matches the pre-run
active_visual byte-for-byte; subsequent dumps show zero null
`timelineStart`.

Exit codes:
  0  applied (or dry-run completed)
  1  invocation problem (missing pass, missing DB)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = (
    REPO_ROOT.parent
    / "ai-agent-video-editor"
    / ".cut-notes"
    / "cut-notes.sqlite"
)
PROJECT_ID = "piano-hand-size-part-2"


def _now_iso() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _clip_duration(row: dict) -> float:
    duration = row.get("targetDuration")
    if duration is None:
        sin = row.get("sourceIn") or 0.0
        sout = row.get("sourceOut") or sin
        duration = max(0.0, sout - sin)
    return float(duration)


def _resolve_starts(rows: list[dict]) -> list[tuple[str, float]]:
    """Mirror dump_timeline.resolve_timeline_starts: clips with NULL
    timelineStart stack after the running cursor; explicit-position
    clips don't advance the cursor. Returns [(id, resolved_start)] for
    every NULL-start clip in iteration order."""
    cursor = 0.0
    out: list[tuple[str, float]] = []
    for row in rows:
        if row.get("timelineStart") is None:
            out.append((row["id"], cursor))
            cursor += _clip_duration(row)
        else:
            # explicit position; don't advance the cursor
            pass
    return out


def run(pass_id: str, dry_run: bool) -> int:
    if not DB_PATH.exists():
        print(f"error: SQLite not found at {DB_PATH}", file=sys.stderr)
        return 1
    mode = "ro" if dry_run else "rwc"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row

    if not conn.execute("SELECT 1 FROM passes WHERE id = ?", (pass_id,)).fetchone():
        print(f"error: pass not found: {pass_id}", file=sys.stderr)
        conn.close()
        return 1

    # Same SELECT order as dump_timeline.fetch_clips so cursor logic
    # produces identical positions.
    rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT id, role, "order", timelineStart, sourceIn, sourceOut,
                   targetDuration, lastEditedBy
            FROM timeline_items
            WHERE projectId = ? AND passId = ? AND enabled = 1
            ORDER BY "order" ASC
            """,
            (PROJECT_ID, pass_id),
        ).fetchall()
    ]

    fills = _resolve_starts(rows)
    if not fills:
        print(f"no NULL timelineStart in {pass_id}; nothing to fill")
        conn.close()
        return 0

    print(f"{pass_id}: {len(fills)} clips need explicit timelineStart")
    for clip_id, start in fills[:10]:
        print(f"  {clip_id:42s} → {start:7.3f}s")
    if len(fills) > 10:
        print(f"  … and {len(fills) - 10} more")

    if dry_run:
        print(f"\ndry-run: would update {len(fills)} rows")
        conn.close()
        return 0

    now = _now_iso()
    try:
        conn.execute("BEGIN")
        for clip_id, start in fills:
            # Stamp lastEditedBy='ai' so the source-of-truth audit trail
            # captures who set the position.
            conn.execute(
                """UPDATE timeline_items
                   SET timelineStart = ?, lastEditedBy = ?, lastEditedAt = ?
                   WHERE id = ?""",
                (float(start), "ai", now, clip_id),
            )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"SQL error: {exc}", file=sys.stderr)
        conn.close()
        return 1
    conn.close()
    print(f"\napplied: {len(fills)} explicit timelineStart values written")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pass_id", help="Pass id to fill")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(args.pass_id, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
