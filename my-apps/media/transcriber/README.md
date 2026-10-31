# transcriber

Writes a Markdown transcript next to every video or audio file in the NAS inbox.

- **Drop a file:** copy any mp4/mkv/mp3/... into `\\192.168.10.133\k8s\media-inbox` (any subfolder).
- **Drop a link:** paste it into [MeTube](https://metube.vanillax.me). It saves into `media-inbox/metube/`.
- About two minutes after the file stops changing, `<name>.md` appears beside it.

How it works: `scripts/transcriber.py` polls the inbox every minute. It cuts the audio into 10-minute mp3 chunks with ffmpeg and sends them to LiteLLM model `whisper` (OpenVINO on the gen12 iGPU, `my-apps/ai/whisper`).

| You see | Meaning | Do |
|---|---|---|
| `<name>.transcribe-error.txt` | The file couldn't be read or was rejected | Fix or replace the file, then delete the marker to retry |
| No `.md`, log says `backend unavailable` | Whisper or LiteLLM is down | Nothing. It retries every minute |

Logs: `kubectl -n transcriber logs deploy/transcriber -f`
