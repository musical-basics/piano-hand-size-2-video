import argparse
import os
import whisper
from pathlib import Path

# Always run from the keyboard-trip root
os.chdir(Path(__file__).resolve().parent.parent)

def transcribe_videos(model_name="base", force=False):
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
            
            if transcript_file.exists() and not force:
                print(f"Skipping {video_file.name}; transcript already exists.")
                continue
                
            print(f"Transcribing {video_file.name} with timestamps...")
            try:
                result = model.transcribe(str(video_file))
                
                with open(transcript_file, "w", encoding="utf-8") as f:
                    for segment in result["segments"]:
                        start = segment["start"]
                        # Convert to MM:SS format
                        minutes = int(start // 60)
                        seconds = int(start % 60)
                        timestamp = f"[{minutes:02d}:{seconds:02d}]"
                        f.write(f"{timestamp} {segment['text'].strip()}\n")
                
                print(f"Done: {transcript_file.name}")
            except Exception as e:
                print(f"Error transcribing {video_file.name}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe project MOV files with timestamps.")
    parser.add_argument("--model", default="base", help="Whisper model to use, default: base")
    parser.add_argument("--force", action="store_true", help="Overwrite existing transcript files")
    args = parser.parse_args()

    transcribe_videos(model_name=args.model, force=args.force)
