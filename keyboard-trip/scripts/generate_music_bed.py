"""
Generate a music bed via Replicate (Stable Audio 2.5).

Usage:
    python3 scripts/generate_music_bed.py "<prompt>" <duration_seconds> <output_basename>

Example:
    python3 scripts/generate_music_bed.py \
        "warm cinematic ambient road-trip bed, soft synth pads, no drums" \
        60 cold_open_bed

Writes the result to keyboard-trip/audio/music/<output_basename>.<ext>
where <ext> is whatever Replicate returns (currently mp3 for Stable
Audio 2.5; the model ignores the output_format param).

Stable Audio 2.5 is roughly $0.05-0.10 per generation. Max duration is 190s.
"""

import json
import sys
import time
from pathlib import Path
from urllib import request, error

REPLICATE_BASE = "https://api.replicate.com/v1"
MODEL_ENDPOINT = "/models/stability-ai/stable-audio-2.5/predictions"
MAX_DURATION = 190
MIN_DURATION = 1

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "audio" / "music"
ENV_FILE = ROOT.parent / ".env.local"


def load_token() -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}. Need REPLICATE_API_TOKEN.")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("REPLICATE_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    sys.exit("REPLICATE_API_TOKEN not found in .env.local")


def http_request(method: str, url: str, headers: dict, body: bytes | None = None) -> tuple[int, bytes]:
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req) as resp:
            return resp.status, resp.read()
    except error.HTTPError as e:
        return e.code, e.read()


def create_prediction(token: str, prompt: str, duration: int) -> dict:
    body = json.dumps({
        "input": {
            "prompt": prompt,
            "duration": duration,
            "output_format": "wav",
        }
    }).encode()
    status, response = http_request(
        "POST",
        REPLICATE_BASE + MODEL_ENDPOINT,
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "wait=60",
        },
        body,
    )
    if status >= 400:
        sys.exit(f"Replicate {status}: {response.decode(errors='replace')}")
    return json.loads(response)


def poll_until_done(token: str, prediction_id: str) -> dict:
    url = f"{REPLICATE_BASE}/predictions/{prediction_id}"
    while True:
        status, response = http_request(
            "GET", url, {"Authorization": f"Bearer {token}"}
        )
        if status >= 400:
            sys.exit(f"Replicate poll {status}: {response.decode(errors='replace')}")
        data = json.loads(response)
        if data.get("status") in ("succeeded", "failed", "canceled"):
            return data
        time.sleep(2)


def download(url: str, dest: Path) -> None:
    status, body = http_request("GET", url, {})
    if status >= 400:
        sys.exit(f"Download {status}: {body[:300]!r}")
    dest.write_bytes(body)


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    prompt = sys.argv[1]
    duration = int(sys.argv[2])
    out_basename = sys.argv[3]

    if duration < MIN_DURATION or duration > MAX_DURATION:
        sys.exit(f"duration must be {MIN_DURATION}..{MAX_DURATION} seconds")
    # Strip any user-supplied extension; we'll append the real one after the
    # generation completes based on what Replicate actually returned.
    if "." in out_basename.rsplit("/", 1)[-1]:
        out_basename = out_basename.rsplit(".", 1)[0]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    token = load_token()
    print(f"Generating {duration}s track with prompt:\n  {prompt!r}")
    prediction = create_prediction(token, prompt, duration)

    if prediction.get("status") not in ("succeeded", "failed", "canceled"):
        print(f"Wait window expired, polling prediction {prediction['id']} ...")
        prediction = poll_until_done(token, prediction["id"])

    if prediction.get("status") != "succeeded":
        sys.exit(f"Generation {prediction.get('status')}: {prediction.get('error')}")

    output = prediction.get("output")
    audio_url = output if isinstance(output, str) else (output[0] if output else None)
    if not audio_url:
        sys.exit(f"No audio URL in output: {prediction}")

    # Honour Replicate's actual output extension. Stable Audio 2.5 currently
    # always returns mp3, but newer model versions may differ.
    url_path = audio_url.split("?", 1)[0]
    ext = url_path.rsplit(".", 1)[-1].lower() if "." in url_path else "mp3"
    if ext not in {"mp3", "wav", "ogg", "m4a", "flac"}:
        ext = "mp3"

    out_path = OUT_DIR / f"{out_basename}.{ext}"
    if out_path.exists():
        sys.exit(f"Refusing to overwrite existing file: {out_path}")

    print(f"Downloading {audio_url} -> {out_path}")
    download(audio_url, out_path)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
