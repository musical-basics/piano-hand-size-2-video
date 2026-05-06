import argparse
import json
import os
import whisper
from pathlib import Path

# Always run from the keyboard-trip root
os.chdir(Path(__file__).resolve().parent.parent)


def transcribe_videos(model_name="base", force=False, words=False):
    """Transcribe MOV files in the project.

    For every clip, writes:
      - <basename>.txt — segment-level timestamps (existing format)
      - <basename>.json — segment + (when --words) word-level timestamps
        (Plan Step 23 / Checklist item 22)

    The JSON is what render_from_timeline.py and apply_timeline_patch.py
    can read to find natural sentence-end cut points instead of using a
    flat +1.5s talking-head buffer.
    """
    print(f"Loading Whisper model ({model_name})...")
    model = whisper.load_model(model_name)

    # Folders to scan
    folders = [
        "footage/01_Trip_Setup",
        "footage/02_Drive_To_Titusville",
        "footage/03_David_Factory_Visit",
        "footage/05_Post_Pickup_Main_Argument",
        "footage/06_Car_Trouble_Return",
        "footage/07_Home_Demo_Payoff",
        "footage/08_Pickups_To_Record",
    ]

    for folder in folders:
        folder_path = Path(folder)
        if not folder_path.exists():
            continue

        print(f"\nScanning folder: {folder}")
        for video_file in folder_path.glob("*.MOV"):
            transcript_file = video_file.with_suffix(".txt")
            json_file = video_file.with_suffix(".json")

            txt_exists = transcript_file.exists()
            json_exists = json_file.exists()
            # Skip only when both expected outputs already exist (or
            # JSON isn't requested) AND --force isn't set.
            if not force:
                if txt_exists and (json_exists or not words):
                    print(f"Skipping {video_file.name}; outputs already exist.")
                    continue

            print(
                f"Transcribing {video_file.name} "
                f"({'word-level' if words else 'segment-level'})..."
            )
            try:
                result = model.transcribe(
                    str(video_file),
                    word_timestamps=words,
                )

                with open(transcript_file, "w", encoding="utf-8") as f:
                    for segment in result["segments"]:
                        start = segment["start"]
                        minutes = int(start // 60)
                        seconds = int(start % 60)
                        timestamp = f"[{minutes:02d}:{seconds:02d}]"
                        f.write(f"{timestamp} {segment['text'].strip()}\n")

                # JSON sibling: one entry per segment, optionally with
                # the per-word array Whisper produces when
                # word_timestamps=True. The shape mirrors Whisper's so
                # tools downstream don't need to re-derive anything.
                segments_out = []
                for segment in result["segments"]:
                    entry = {
                        "id": segment.get("id"),
                        "text": segment.get("text", "").strip(),
                        "start": float(segment.get("start", 0.0)),
                        "end": float(segment.get("end", 0.0)),
                    }
                    if words and segment.get("words"):
                        entry["words"] = [
                            {
                                "word": w.get("word", "").strip(),
                                "start": float(w.get("start", 0.0)),
                                "end": float(w.get("end", 0.0)),
                                "probability": float(w.get("probability", 0.0)),
                            }
                            for w in segment["words"]
                        ]
                    segments_out.append(entry)

                with json_file.open("w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "source": str(video_file),
                            "language": result.get("language"),
                            "model": model_name,
                            "transcript_segments": segments_out,
                        },
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

                print(f"Done: {transcript_file.name} + {json_file.name}")
            except Exception as e:
                print(f"Error transcribing {video_file.name}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transcribe project MOV files with timestamps.",
    )
    parser.add_argument("--model", default="base", help="Whisper model to use, default: base")
    parser.add_argument("--force", action="store_true", help="Overwrite existing transcript files")
    parser.add_argument(
        "--words",
        action="store_true",
        help="Emit word-level timestamps in the JSON sibling (Plan Step 23).",
    )
    args = parser.parse_args()

    transcribe_videos(model_name=args.model, force=args.force, words=args.words)
