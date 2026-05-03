"""
Regenerate the VO_02..VO_06 voiceovers from TRAVEL_VO_SCRIPT.md using Cartesia.

Workflow:
  1. Re-clones the voice from a new source recording (replaces the existing voice).
  2. Reads VO_02..VO_06 sections from TRAVEL_VO_SCRIPT.md.
  3. Synthesizes each segment via Cartesia /tts/bytes and writes a wav file.
  4. Updates CARTESIA_VOICE.md, VOICEOVER_MANIFEST.md, and cartesia_voice_clone_response.json.

VO_01 is intentionally skipped — that file holds Lionel's real recording.

Usage:
    python3 scripts/regenerate_voiceovers.py
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib import request, error

CARTESIA_VERSION = "2026-03-01"
CARTESIA_BASE = "https://api.cartesia.ai"
TTS_MODEL = "sonic-3"
LANGUAGE = "en"
VOICE_NAME = "Lionel Piano Hand Size VO"
VOICE_DESC = "Voice clone for Piano Hand Size Part 2 narration"

# Paths
ROOT = Path(__file__).resolve().parent.parent
VO_DIR = ROOT / "audio" / "voiceovers"
SCRIPT_FILE = VO_DIR / "TRAVEL_VO_SCRIPT.md"
SOURCE_WAV = VO_DIR / "VO_01_late_night_drive.wav"
CARTESIA_VOICE_MD = VO_DIR / "CARTESIA_VOICE.md"
CLONE_RESPONSE_JSON = VO_DIR / "cartesia_voice_clone_response.json"
MANIFEST_MD = VO_DIR / "VOICEOVER_MANIFEST.md"
ENV_FILE = ROOT.parent / ".env.local"

# Output spec for the TTS files (matches existing VO_02..VO_06).
OUTPUT_FORMAT = {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100}

# Map VO section heading -> output filename
VO_FILES = {
    "VO 02 - Gas Station And Snacks": "VO_02_gas_station_and_snacks.wav",
    "VO 03 - Car Nap": "VO_03_car_nap.wav",
    "VO 04 - Pennsylvania Road": "VO_04_pennsylvania_road.wav",
    "VO 05 - Lake Pause": "VO_05_lake_pause.wav",
    "VO 06 - Breakdown And Return": "VO_06_breakdown_and_return.wav",
}


def load_api_key() -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}. Need CARTESIA_API_KEY.")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("CARTESIA_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("CARTESIA_API_KEY not found in .env.local")


def load_existing_voice_id() -> str | None:
    if CLONE_RESPONSE_JSON.exists():
        try:
            return json.loads(CLONE_RESPONSE_JSON.read_text())["id"]
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def parse_script(text: str) -> dict[str, str]:
    """Return { 'VO 02 - Gas Station And Snacks': '...transcript...' } from the markdown."""
    sections: dict[str, str] = {}
    for match in re.finditer(
        r"^##\s+(VO\s+\d+\s+-\s+[^\n]+)\n(?:[^\n`]*\n)*?```text\n(.*?)\n```",
        text,
        re.MULTILINE | re.DOTALL,
    ):
        heading = match.group(1).strip()
        body = match.group(2).strip()
        sections[heading] = body
    return sections


def http_request(method: str, url: str, headers: dict, body: bytes | None = None) -> tuple[int, bytes, dict]:
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req) as resp:
            return resp.status, resp.read(), dict(resp.getheaders())
    except error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})


def delete_voice(api_key: str, voice_id: str) -> None:
    print(f"Deleting old voice {voice_id} ...")
    status, body, _ = http_request(
        "DELETE",
        f"{CARTESIA_BASE}/voices/{voice_id}",
        {"Cartesia-Version": CARTESIA_VERSION, "Authorization": f"Bearer {api_key}"},
    )
    if status not in (200, 204, 404):
        print(f"  warning: delete returned {status}: {body[:200]!r}")
    else:
        print(f"  deleted (status {status})")


def clone_voice(api_key: str, source_path: Path) -> dict:
    """Multipart upload of the source audio to /voices/clone."""
    print(f"Cloning new voice from {source_path.name} ...")
    boundary = "----CartesiaBoundary7d8c2f3e1a"
    crlf = b"\r\n"
    parts: list[bytes] = []

    def add_text(name: str, value: str) -> None:
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode())

    add_text("name", VOICE_NAME)
    add_text("description", VOICE_DESC)
    add_text("language", LANGUAGE)

    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="clip"; filename="{source_path.name}"'.encode()
    )
    parts.append(b"Content-Type: audio/wav")
    parts.append(b"")
    parts.append(source_path.read_bytes())

    parts.append(f"--{boundary}--".encode())
    parts.append(b"")
    body = crlf.join(parts)

    status, resp_bytes, _ = http_request(
        "POST",
        f"{CARTESIA_BASE}/voices/clone",
        {
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body,
    )
    if status != 200:
        sys.exit(f"Voice clone failed ({status}): {resp_bytes[:500]!r}")
    voice = json.loads(resp_bytes)
    print(f"  new voice id: {voice['id']}")
    return voice


def synthesize(api_key: str, voice_id: str, text: str, out_path: Path) -> None:
    print(f"  synthesizing -> {out_path.name} ({len(text.split())} words)")
    body = json.dumps(
        {
            "model_id": TTS_MODEL,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "language": LANGUAGE,
            "output_format": OUTPUT_FORMAT,
        }
    ).encode()
    status, audio, _ = http_request(
        "POST",
        f"{CARTESIA_BASE}/tts/bytes",
        {
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body,
    )
    if status != 200:
        sys.exit(f"  TTS failed ({status}): {audio[:500]!r}")
    out_path.write_bytes(audio)


def wav_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)]
    )
    return float(out.strip())


def update_cartesia_voice_md(voice: dict) -> None:
    CARTESIA_VOICE_MD.write_text(
        f"""# Cartesia Voice

Voice name: {voice['name']}

Voice ID:

```text
{voice['id']}
```

Source reference:

```text
audio/voiceovers/VO_01_late_night_drive.wav
```

Created:

```text
{voice['created_at']}
```
"""
    )


def update_manifest_md(voice_id: str, durations: dict[str, float]) -> None:
    placements = {
        "VO_01_late_night_drive.wav": "After the front-facing intro / over late-night drive setup.",
        "VO_02_gas_station_and_snacks.wav": "Over gas station and snack montage.",
        "VO_03_car_nap.wav": "Over car nap and waking-up beat.",
        "VO_04_pennsylvania_road.wav": "Over Pennsylvania road texture and almost-there section.",
        "VO_05_lake_pause.wav": "Over lake pause after David factory visit.",
        "VO_06_breakdown_and_return.wav": "Over breakdown / return-home section.",
    }
    rows = ["| file | duration | source | intended placement |",
            "| --- | ---: | --- | --- |"]
    for fname, placement in placements.items():
        dur = durations.get(fname)
        dur_s = f"{dur:.2f}s" if dur is not None else "—"
        source = "Lionel real recording" if fname.startswith("VO_01") else "Cartesia TTS"
        rows.append(f"| `{fname}` | {dur_s} | {source} | {placement} |")
    table = "\n".join(rows)

    MANIFEST_MD.write_text(
        f"""# Voiceover Manifest

VO_01 is Lionel's real recording (bounced from Logic).
VO_02..VO_06 are generated with Cartesia voice `{VOICE_NAME}`, cloned from
the VO_01 recording for vocal consistency.

Voice ID:

```text
{voice_id}
```

## Travel VO Files

{table}

## Notes

- Output format: WAV, 44.1 kHz, 16-bit PCM (TTS files).
- VO_01 is 48 kHz stereo PCM s16 from Logic; the cut script normalises sample rates.
- Keep natural location audio where it adds texture, but duck it under the VO.
- Regenerate any TTS chunk that feels too slow, too flat, or too AI-clean by re-running
  `python3 scripts/regenerate_voiceovers.py`.
"""
    )


def main() -> None:
    api_key = load_api_key()
    script_text = SCRIPT_FILE.read_text()
    sections = parse_script(script_text)

    missing = [k for k in VO_FILES if k not in sections]
    if missing:
        sys.exit(f"Missing sections in {SCRIPT_FILE.name}: {missing}")

    if not SOURCE_WAV.exists():
        sys.exit(f"Source recording not found: {SOURCE_WAV}")

    old_id = load_existing_voice_id()
    if old_id:
        delete_voice(api_key, old_id)

    voice = clone_voice(api_key, SOURCE_WAV)
    voice_id = voice["id"]
    CLONE_RESPONSE_JSON.write_text(json.dumps(voice) + "\n")
    update_cartesia_voice_md(voice)

    for heading, fname in VO_FILES.items():
        synthesize(api_key, voice_id, sections[heading], VO_DIR / fname)

    durations: dict[str, float] = {}
    for fname in ["VO_01_late_night_drive.wav", *VO_FILES.values()]:
        path = VO_DIR / fname
        if path.exists():
            durations[fname] = wav_duration(path)

    update_manifest_md(voice_id, durations)
    print("\nDone.")
    for fname, dur in durations.items():
        print(f"  {fname}: {dur:.2f}s")


if __name__ == "__main__":
    main()
