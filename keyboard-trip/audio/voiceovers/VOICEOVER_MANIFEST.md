# Voiceover Manifest

VO_01 is Lionel's real recording (bounced from Logic).
VO_02..VO_06 are generated with Cartesia voice `Lionel Piano Hand Size VO`, cloned from
the VO_01 recording for vocal consistency.

Voice ID:

```text
cba3c82a-4099-489c-acb0-4e927e89eeed
```

## Travel VO Files

| file | duration | source | intended placement |
| --- | ---: | --- | --- |
| `VO_01_late_night_drive.wav` | 39.91s | Lionel real recording | After the front-facing intro / over late-night drive setup. |
| `VO_02_gas_station_and_snacks.wav` | 17.28s | Cartesia TTS | Over gas station and snack montage. |
| `VO_03_car_nap.wav` | 14.40s | Cartesia TTS | Over car nap and waking-up beat. |
| `VO_04_pennsylvania_road.wav` | 18.39s | Cartesia TTS | Over Pennsylvania road texture and almost-there section. |
| `VO_05_lake_pause.wav` | 10.68s | Cartesia TTS | Over lake pause after David factory visit. |
| `VO_06_breakdown_and_return.wav` | 17.65s | Cartesia TTS | Over breakdown / return-home section. |

## Notes

- Output format: WAV, 44.1 kHz, 16-bit PCM (TTS files).
- VO_01 is 48 kHz stereo PCM s16 from Logic; the cut script normalises sample rates.
- Keep natural location audio where it adds texture, but duck it under the VO.
- Regenerate any TTS chunk that feels too slow, too flat, or too AI-clean by re-running
  `python3 scripts/regenerate_voiceovers.py`.
