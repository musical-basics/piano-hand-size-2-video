#!/usr/bin/env python3
"""
Export the current Cut Notes timeline pass to an editable Final Cut Pro XML.

The export intentionally mirrors scripts/dump_timeline.py's timing rules:
clips without timelineStart advance a running cursor, while explicitly placed
clips sit at their requested time without moving the cursor. That keeps this
FCPXML aligned with the rendered review cut and the editor database.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
DB_PATH = WORKSPACE / "ai-agent-video-editor" / ".cut-notes" / "cut-notes.sqlite"
EXPORT_DIR = ROOT / "exports" / "fcpxml"
PROJECT_ID = "piano-hand-size-part-2"

PROJECT_WIDTH = 1280
PROJECT_HEIGHT = 720
PROJECT_FPS = 30

VISUAL_PRIORITY = {
    "a_roll": 0,
    "b_roll": 1,
    "still": 2,
    "title_card": 3,
    "placeholder": 4,
    "ambient": 5,
}
AUDIO_ROLES = {"voiceover", "music"}
TITLE_ROLES = {"title_card", "placeholder"}

MUSIC_CARD_DB = 20 * math.log10(0.28)
MUSIC_UNDER_VO_DB = 20 * math.log10(0.24)


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(f"SQLite not found: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def parse_metadata(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def current_pass_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT metadata FROM projects WHERE id = ?", (PROJECT_ID,)
    ).fetchone()
    if not row:
        sys.exit(f"Unknown project: {PROJECT_ID}")
    metadata = parse_metadata(row["metadata"])
    pass_id = metadata.get("currentPassId")
    if not pass_id:
        sys.exit("Project metadata does not include currentPassId")
    return str(pass_id)


def fetch_pass(conn: sqlite3.Connection, pass_id: str) -> sqlite3.Row:
    row = conn.execute(
        'SELECT id, name, status FROM passes WHERE projectId = ? AND id = ?',
        (PROJECT_ID, pass_id),
    ).fetchone()
    if not row:
        sys.exit(f"Unknown pass: {pass_id}")
    return row


def fetch_clips(conn: sqlite3.Connection, pass_id: str) -> list[dict[str, Any]]:
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
          a.hasAudio AS assetHasAudio, a.metadata AS assetMetadata
        FROM timeline_items ti
        LEFT JOIN assets a ON a.id = ti.assetId
        WHERE ti.projectId = ?
          AND ti.passId = ?
          AND ti.enabled = 1
        ORDER BY ti."order" ASC
        """,
        (PROJECT_ID, pass_id),
    ).fetchall()
    clips = [dict(row) for row in rows]
    resolve_timeline_starts(clips)
    return clips


def resolve_timeline_starts(clips: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for clip in clips:
        if clip.get("timelineStart") is None:
            clip["_resolved_start"] = cursor
            cursor += clip_duration(clip)
        else:
            clip["_resolved_start"] = float(clip["timelineStart"])


def clip_duration(clip: dict[str, Any]) -> float:
    duration = clip.get("targetDuration")
    if duration is None:
        source_in = clip.get("sourceIn") or 0.0
        source_out = clip.get("sourceOut") or source_in
        duration = max(0.0, float(source_out) - float(source_in))
    return float(duration)


def clip_window(clip: dict[str, Any]) -> tuple[float, float]:
    start = float(clip["_resolved_start"])
    return start, start + clip_duration(clip)


def is_visual(clip: dict[str, Any]) -> bool:
    return clip["role"] in VISUAL_PRIORITY


def is_audio(clip: dict[str, Any]) -> bool:
    return clip["role"] in AUDIO_ROLES


def source_path(clip: dict[str, Any]) -> Path | None:
    metadata = parse_metadata(clip.get("assetMetadata"))
    rel = metadata.get("relativePath")
    if rel:
        return (ROOT / str(rel)).resolve()
    asset_path = clip.get("assetPath")
    if not asset_path:
        return None
    path = Path(str(asset_path))
    if path == ROOT or path.is_dir():
        return None
    return path.resolve()


def fcptime(seconds: float | int | None) -> str:
    value = 0.0 if seconds is None else float(seconds)
    if abs(value) < 0.0000005:
        return "0s"
    frac = Fraction(str(round(value, 6))).limit_denominator(1_000_000)
    return fraction_time(frac)


def fraction_time(frac: Fraction) -> str:
    if frac.denominator == 1:
        return f"{frac.numerator}s"
    return f"{frac.numerator}/{frac.denominator}s"


def attr_float(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def db_amount(value: float) -> str:
    return f"{value:.1f}dB"


def clean_name(value: str | None, fallback: str) -> str:
    text = (value or fallback).strip()
    return " ".join(text.split()) or fallback


def title_preview(text: str) -> str:
    return clean_name(text.replace("\n", " "), "Title")[:42]


def probe_media(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,avg_frame_rate,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return {}
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    info: dict[str, Any] = {}
    duration = data.get("format", {}).get("duration")
    if duration not in (None, "N/A"):
        try:
            info["duration"] = float(duration)
        except ValueError:
            pass

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and "width" not in info:
            info["width"] = int(stream.get("width") or PROJECT_WIDTH)
            info["height"] = int(stream.get("height") or PROJECT_HEIGHT)
            info["avg_frame_rate"] = stream.get("avg_frame_rate")
        if codec_type == "audio" and "audio_rate" not in info:
            sample_rate = stream.get("sample_rate")
            channels = stream.get("channels")
            info["audio_rate"] = int(sample_rate) if sample_rate else 48000
            info["audio_channels"] = int(channels) if channels else 2
    return info


def format_key(info: dict[str, Any], fallback_kind: str) -> tuple[int, int, str]:
    width = int(info.get("width") or PROJECT_WIDTH)
    height = int(info.get("height") or PROJECT_HEIGHT)
    if fallback_kind == "image":
        return width, height, "undefined"
    # The rough-cut render normalizes everything to 30fps, and using one clean
    # project-rate resource avoids tiny phone-camera VFR fractions in FCP.
    return width, height, str(PROJECT_FPS)


def frame_duration(rate: str) -> str | None:
    if rate == "undefined":
        return None
    try:
        frac = Fraction(rate)
    except (ValueError, ZeroDivisionError):
        frac = Fraction(PROJECT_FPS, 1)
    if frac <= 0:
        frac = Fraction(PROJECT_FPS, 1)
    duration = Fraction(frac.denominator, frac.numerator)
    return fraction_time(duration)


def add_format_resource(
    resources: Element,
    fmt_id: str,
    width: int,
    height: int,
    rate: str,
    project: bool = False,
) -> None:
    attrs = {
        "id": fmt_id,
        "name": (
            f"FFVideoFormat{height}p{PROJECT_FPS}"
            if project or rate != "undefined"
            else "FFVideoFormatRateUndefined"
        ),
        "width": str(width),
        "height": str(height),
        "colorSpace": "1-1-1 (Rec. 709)",
    }
    dur = frame_duration(rate)
    if dur:
        attrs["frameDuration"] = dur
    SubElement(resources, "format", attrs)


def build_media_resources(
    resources: Element,
    clips: list[dict[str, Any]],
    first_resource_id: int = 2,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[str]]:
    media_clips = [
        c for c in clips
        if c.get("assetId") and c["role"] not in TITLE_ROLES and source_path(c)
    ]
    assets: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for clip in media_clips:
        asset_id = str(clip["assetId"])
        path = source_path(clip)
        if not path:
            continue
        entry = assets.setdefault(
            asset_id,
            {
                "asset_id": asset_id,
                "basename": clean_name(clip.get("assetBasename"), path.name),
                "kind": clip.get("assetKind") or "video",
                "path": path,
                "has_audio": bool(clip.get("assetHasAudio")),
                "duration": clip.get("assetDuration"),
                "usage": [],
            },
        )
        entry["usage"].append(clip)

    for asset in assets.values():
        path = asset["path"]
        info = probe_media(path)
        if not path.exists():
            warnings.append(f"missing media: {path}")
        asset["probe"] = info
        if info.get("duration"):
            asset["duration"] = info["duration"]
        elif asset["duration"] is None:
            max_source_out = 0.0
            for clip in asset["usage"]:
                source_in = clip.get("sourceIn") or 0.0
                source_out = clip.get("sourceOut")
                if source_out is None:
                    source_out = float(source_in) + clip_duration(clip)
                max_source_out = max(max_source_out, float(source_out))
            asset["duration"] = max(max_source_out, 3600.0 if asset["kind"] == "image" else max_source_out)

        if asset["kind"] == "image":
            # Still images can be stretched to any edit duration in Final Cut.
            asset["duration"] = max(float(asset.get("duration") or 0.0), 3600.0)
            asset["has_audio"] = False
        elif info.get("audio_rate"):
            asset["has_audio"] = True

    format_ids: dict[tuple[int, int, str], str] = {
        (PROJECT_WIDTH, PROJECT_HEIGHT, str(PROJECT_FPS)): "r1"
    }
    next_resource = first_resource_id
    asset_resource_ids: dict[str, str] = {}

    for asset_id, asset in sorted(assets.items(), key=lambda item: item[1]["basename"]):
        kind = str(asset["kind"])
        info = asset.get("probe") or {}
        is_visual_asset = kind in {"video", "image"} or info.get("width")
        fmt_id = ""
        if is_visual_asset:
            key = format_key(info, "image" if kind == "image" else "video")
            if key not in format_ids:
                fmt_id = f"r{next_resource}"
                next_resource += 1
                format_ids[key] = fmt_id
                add_format_resource(resources, fmt_id, key[0], key[1], key[2])
            else:
                fmt_id = format_ids[key]

        resource_id = f"r{next_resource}"
        next_resource += 1
        asset_resource_ids[asset_id] = resource_id
        attrs = {
            "id": resource_id,
            "name": asset["basename"],
            "start": "0s",
            "duration": fcptime(asset["duration"]),
        }
        if is_visual_asset:
            attrs["hasVideo"] = "1"
            attrs["format"] = fmt_id or "r1"
        if asset["has_audio"]:
            attrs.update(
                {
                    "hasAudio": "1",
                    "audioSources": "1",
                    "audioChannels": str((info or {}).get("audio_channels") or 2),
                    "audioRate": str((info or {}).get("audio_rate") or 48000),
                }
            )
        asset_el = SubElement(resources, "asset", attrs)
        SubElement(
            asset_el,
            "media-rep",
            {
                "kind": "original-media",
                "src": asset["path"].as_uri(),
            },
        )
    return asset_resource_ids, assets, warnings


def windows_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return min(a[1], b[1]) - max(a[0], b[0]) > 0.001


def overlaps_voiceover(
    clip: dict[str, Any], voiceover_windows: list[tuple[float, float]]
) -> bool:
    window = clip_window(clip)
    return any(windows_overlap(window, vo) for vo in voiceover_windows)


def rotation_value(clip: dict[str, Any]) -> str | None:
    value = clip.get("rotationOverride")
    if value is None:
        value = clip.get("assetRotation")
    try:
        degrees = int(value or 0)
    except (TypeError, ValueError):
        return None
    if degrees % 360 == 0:
        return None
    if degrees % 360 == 270:
        return "-90"
    return str(degrees % 360)


def title_params(title_el: Element, mode: str) -> None:
    if mode == "card":
        position = "0 0"
        anchor = "640 360"
        right_margin = "1280"
        top_margin = "120"
    else:
        position = "0 -232"
        anchor = "640 360"
        right_margin = "1128"
        top_margin = "0"

    params = [
        ("Alignment", "9999/11020/10003/10009/2/354/10038/401", "1 (center)"),
        ("Alignment", "9999/11020/10003/10009/2/373", "0 (Left) 1 (Middle)"),
        ("Build Out", "9999/10000/2/102", "0"),
        ("Shadow", "9999/11944/100/11946/2/100", "0"),
        ("Position", "9999/11020/10003/10009/1/100/101", position),
        ("Layour Method", "9999/11020/10003/10009/2/314", "1 (Paragraph)"),
        ("Anchor Point", "9999/11020/10003/10009/1/100/107", anchor),
        ("Right Margin", "9999/11020/10003/10009/2/324", right_margin),
        ("Top Margin", "9999/11020/10003/10009/2/325", top_margin),
        ("Build In", "9999/10000/2/101", "0"),
    ]
    for name, key, value in params:
        SubElement(title_el, "param", {"name": name, "key": key, "value": value})


def add_title(
    parent: Element,
    text: str,
    offset: float,
    duration: float,
    lane: int,
    style_id: str,
    mode: str,
) -> None:
    title_el = SubElement(
        parent,
        "title",
        {
            "name": f"{title_preview(text)} - Caption",
            "ref": "r2",
            "lane": str(lane),
            "offset": fcptime(offset),
            "duration": fcptime(duration),
            "start": "0s",
            "role": "titles.Generated Titles",
        },
    )
    title_params(title_el, mode)
    text_el = SubElement(title_el, "text")
    text_style = SubElement(text_el, "text-style", {"ref": style_id})
    text_style.text = text
    style_def = SubElement(title_el, "text-style-def", {"id": style_id})
    if mode == "card":
        font_size = "40"
        line_spacing = "14"
    else:
        font_size = "34"
        line_spacing = "8"
    SubElement(
        style_def,
        "text-style",
        {
            "font": "Arial",
            "fontFace": "Bold",
            "fontSize": font_size,
            "fontColor": "1 1 1 1",
            "alignment": "center",
            "lineSpacing": line_spacing,
        },
    )


def add_native_caption(
    parent: Element,
    text: str,
    offset: float,
    duration: float,
    lane: int,
    style_id: str,
) -> None:
    caption_text = " ".join(text.split())
    caption_el = SubElement(
        parent,
        "caption",
        {
            "name": title_preview(caption_text),
            "lane": str(lane),
            "offset": fcptime(offset),
            "duration": fcptime(duration),
            "start": "0s",
            "role": "iTT?captionFormat=ITT.en",
        },
    )
    text_el = SubElement(caption_el, "text", {"placement": "bottom"})
    text_style = SubElement(text_el, "text-style", {"ref": style_id})
    text_style.text = caption_text
    style_def = SubElement(caption_el, "text-style-def", {"id": style_id})
    SubElement(
        style_def,
        "text-style",
        {
            "font": ".AppleSystemUIFont",
            "fontFace": "Regular",
            "fontSize": "13",
            "fontColor": "1.0 1.0 1.0 1.0",
            "backgroundColor": "0.0 0.0 0.0 1.0",
        },
    )


def add_text_overlay(
    parent: Element,
    text: str,
    offset: float,
    duration: float,
    lane: int,
    style_id: str,
    mode: str,
    title_mode: str,
) -> None:
    if title_mode == "none":
        return
    if title_mode == "native":
        add_native_caption(parent, text, offset, duration, lane, style_id)
        return
    add_title(parent, text, offset, duration, lane, style_id, mode)


def add_visual_clip(
    parent: Element,
    clip: dict[str, Any],
    ref: str,
    asset: dict[str, Any],
    mute_source_audio: bool,
) -> None:
    start, _ = clip_window(clip)
    attrs = {
        "name": clean_name(clip.get("assetBasename"), clip["id"]),
        "ref": ref,
        "lane": "1",
        "offset": fcptime(start),
        "duration": fcptime(clip_duration(clip)),
        "start": fcptime(clip.get("sourceIn") or 0.0),
        "tcFormat": "NDF",
    }
    if asset.get("has_audio"):
        attrs["audioRole"] = "dialogue"
    clip_el = SubElement(parent, "asset-clip", attrs)
    SubElement(clip_el, "adjust-conform", {"type": "fit"})
    rotation = rotation_value(clip)
    if rotation:
        SubElement(clip_el, "adjust-transform", {"rotation": rotation})
    if mute_source_audio and asset.get("has_audio"):
        SubElement(clip_el, "adjust-volume", {"amount": "-96dB"})


def add_audio_clip(
    parent: Element,
    clip: dict[str, Any],
    ref: str,
    asset: dict[str, Any],
) -> None:
    start, _ = clip_window(clip)
    role = "music" if clip["role"] == "music" else "dialogue"
    lane = "-2" if clip["role"] == "music" else "-1"
    attrs = {
        "name": clean_name(clip.get("assetBasename"), clip["id"]),
        "ref": ref,
        "lane": lane,
        "offset": fcptime(start),
        "duration": fcptime(clip_duration(clip)),
        "start": fcptime(clip.get("sourceIn") or 0.0),
        "audioRole": role,
    }
    clip_el = SubElement(parent, "asset-clip", attrs)
    if clip["role"] == "music":
        amount = MUSIC_CARD_DB if ("cold" in clip["id"] or "p056" in clip["id"]) else MUSIC_UNDER_VO_DB
        SubElement(clip_el, "adjust-volume", {"amount": db_amount(amount)})
    elif asset.get("probe", {}).get("audio_rate") and asset["probe"]["audio_rate"] != 48000:
        SubElement(clip_el, "adjust-volume", {"amount": "0dB"})


def build_fcpxml(
    pass_row: sqlite3.Row,
    clips: list[dict[str, Any]],
    title_mode: str,
) -> tuple[str, list[str]]:
    total_duration = max((clip_window(c)[1] for c in clips), default=0.0)

    fcpxml = Element("fcpxml", {"version": "1.10"})
    resources = SubElement(fcpxml, "resources")
    add_format_resource(
        resources,
        "r1",
        PROJECT_WIDTH,
        PROJECT_HEIGHT,
        str(PROJECT_FPS),
        project=True,
    )
    if title_mode == "captionator":
        SubElement(
            resources,
            "effect",
            {
                "id": "r2",
                "name": "Caption",
                "uid": "~/Titles.localized/Captionator/Caption/Caption.moti",
            },
        )
    asset_refs, assets, warnings = build_media_resources(
        resources,
        clips,
        first_resource_id=3 if title_mode == "captionator" else 2,
    )

    library = SubElement(fcpxml, "library")
    event = SubElement(
        library,
        "event",
        {
            "name": "Piano Hand Size Part 2",
            "uid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{PROJECT_ID}:event")).upper(),
        },
    )
    project = SubElement(
        event,
        "project",
        {
            "name": f"{pass_row['name']} FCPXML",
            "uid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{PROJECT_ID}:{pass_row['id']}")).upper(),
            "modDate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000"),
        },
    )
    sequence = SubElement(
        project,
        "sequence",
        {
            "duration": fcptime(total_duration),
            "format": "r1",
            "tcStart": "0s",
            "tcFormat": "NDF",
            "audioLayout": "stereo",
            "audioRate": "48k",
        },
    )
    spine = SubElement(sequence, "spine")
    timeline_gap = SubElement(
        spine,
        "gap",
        {
            "name": "Pass 15 Timeline",
            "offset": "0s",
            "start": "0s",
            "duration": fcptime(total_duration),
        },
    )

    voiceover_windows = [
        clip_window(c) for c in clips if c["role"] == "voiceover"
    ]
    title_index = 0

    for clip in clips:
        if not is_visual(clip):
            continue
        start, _ = clip_window(clip)
        duration = clip_duration(clip)
        overlay = clip.get("textOverlay")
        if clip["role"] in TITLE_ROLES:
            if overlay:
                title_index += 1
                add_text_overlay(
                    timeline_gap,
                    overlay,
                    start,
                    duration,
                    lane=2,
                    style_id=f"ts{title_index}",
                    mode="card",
                    title_mode=title_mode,
                )
            continue

        asset_id = str(clip.get("assetId") or "")
        ref = asset_refs.get(asset_id)
        asset = assets.get(asset_id)
        if ref and asset:
            add_visual_clip(
                timeline_gap,
                clip,
                ref,
                asset,
                mute_source_audio=overlaps_voiceover(clip, voiceover_windows),
            )
        else:
            warnings.append(f"skipped visual clip without media: {clip['id']}")

        if overlay:
            title_index += 1
            add_text_overlay(
                timeline_gap,
                overlay,
                start,
                duration,
                lane=3,
                style_id=f"ts{title_index}",
                mode="caption",
                title_mode=title_mode,
            )

    for clip in clips:
        if not is_audio(clip):
            continue
        asset_id = str(clip.get("assetId") or "")
        ref = asset_refs.get(asset_id)
        asset = assets.get(asset_id)
        if not ref or not asset:
            warnings.append(f"skipped audio clip without media: {clip['id']}")
            continue
        add_audio_clip(timeline_gap, clip, ref, asset)

    raw = tostring(fcpxml, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="    ", encoding="UTF-8")
    text = pretty.decode("utf-8")
    text = text.replace("<?xml version=\"1.0\" encoding=\"UTF-8\"?>", "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE fcpxml>")
    return text, warnings


def default_output(pass_id: str) -> Path:
    suffix = pass_id.replace("pass-15-captions-travel-chronology", "pass15_v12")
    return EXPORT_DIR / f"piano_hand_size_part2_{suffix}.fcpxml"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pass_id",
        nargs="?",
        help="Pass ID to export. Defaults to project metadata currentPassId.",
    )
    parser.add_argument("--output", type=Path, help="Output .fcpxml path")
    parser.add_argument(
        "--title-mode",
        choices=("native", "captionator", "none"),
        default="native",
        help=(
            "How to export text overlays. 'native' writes FCP iTT captions "
            "and is the safest importer path."
        ),
    )
    args = parser.parse_args()

    conn = open_db()
    pass_id = args.pass_id or current_pass_id(conn)
    pass_row = fetch_pass(conn, pass_id)
    clips = fetch_clips(conn, pass_id)
    output = (args.output or default_output(pass_id)).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    text, warnings = build_fcpxml(pass_row, clips, args.title_mode)
    output.write_text(text, encoding="utf-8")

    visual_count = sum(1 for c in clips if is_visual(c))
    audio_count = sum(1 for c in clips if is_audio(c))
    caption_count = sum(1 for c in clips if c.get("textOverlay"))
    total = max((clip_window(c)[1] for c in clips), default=0.0)
    print(f"[fcpxml] wrote {display_path(output)}")
    print(
        f"[fcpxml] {len(clips)} clips: {visual_count} visual, "
        f"{audio_count} audio, {caption_count} text overlays "
        f"({args.title_mode}), "
        f"{total:.1f}s total"
    )
    if warnings:
        print(f"[fcpxml] warnings: {len(warnings)}")
        for warning in warnings[:10]:
            print(f"  - {warning}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")


if __name__ == "__main__":
    main()
