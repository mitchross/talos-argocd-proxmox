---
name: video-transcribe
description: Use when asked to transcribe a video link or file.
---

# Video transcribe (manual, in chat)

Mitch wants transcription only on demand in a Hermes chat. Never set up watchers, cron jobs or background auto-transcription for it.

Flow: MeTube downloads the link (yt-dlp lives there, not in Hermes) -> Hermes pulls the audio file over HTTP -> ffmpeg -> LiteLLM model `whisper` (OpenVINO on the gen12 iGPU) -> Hermes writes the transcript and summarizes.

| Piece | Address (in-cluster) |
|---|---|
| MeTube API | `http://metube.metube.svc.cluster.local:8081` (LAN UI `https://metube.vanillax.me`) |
| Downloaded files | `$M/download/<filename>` (also on the NAS at `\\192.168.10.133\k8s\media-inbox\metube`) |
| Whisper | LiteLLM model `whisper`, `http://litellm-service.litellm.svc.cluster.local:4000/v1`, key `$LITELLM_API_KEY` |

Apps: `my-apps/media/metube`, `my-apps/ai/whisper` in talos-argocd-proxmox. If one isn't running (`kubectl get pods -n metube`, `-n whisper`), say so, then use the captions fallback below.

**Captions fallback (YouTube only, also the fastest path when the video has captions):** `/opt/hermes/.venv/bin/python /opt/data/skills/media/youtube-content/scripts/fetch_transcript.py <id> --text-only --timestamps > $W/yt.txt`. It needs no Whisper or MeTube and returns in seconds. Say which path produced the transcript.

**Several videos:** queue them all in MeTube at once (one `/add` per id). Then hand each long transcript to a `codex` or `fast` subagent with Mitch's setup in the context, asking for timestamped points plus an "idea | already have it? | worth adopting?" table. This keeps 100k+ characters of transcript out of the Opus main chat.

## 1. Get an audio file
**Link:** queue audio only, poll, then download it into the scratch dir.
```bash
M=http://metube.metube.svc.cluster.local:8081
curl -s $M/add -H 'Content-Type: application/json' \
  -d '{"url":"<URL>","download_type":"audio","format":"mp3","quality":"best"}'   # expect {"status": "ok"}
# poll every ~10 s: entry in .done whose url matches; status finished -> .filename, error -> .msg
curl -s $M/history
W=/opt/data/cache/scratch/yt-<video-id>; mkdir -p $W; curl -sf -o "$W/in.mp3" "$M/download/$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$FILENAME")"
```
**File** Mitch attached or a path in the pod: use it directly as the input.

## 2. Transcribe
```bash
ffmpeg -nostdin -loglevel error -i "<input>" -vn -ac 1 -ar 16000 -c:a libmp3lame -b:a 48k \
  -f segment -segment_time 600 -reset_timestamps 1 "$W/chunk%04d.mp3"
for c in "$W"/chunk*.mp3; do
  curl -s http://litellm-service.litellm.svc.cluster.local:4000/v1/audio/transcriptions \
    -H "Authorization: Bearer $LITELLM_API_KEY" -F model=whisper -F file=@"$c" \
    -F response_format=verbose_json -F 'timestamp_granularities[]=segment' > "$c.json"
done
```
Chunk N's segment times start at N×600 s; build `[hh:mm:ss] text` lines in Python. Speed: ~6x realtime (14-min speech in 135 s). Run long jobs with `background=true, notify_on_complete=true`.

## 3. Deliver
- **Mitch's own recordings** (meetings, voice notes, files he attached): write the transcript to `/opt/data/workspace/transcripts/<title>.md` and hand it over with `MEDIA:`. Lead with a short summary that cites timestamps.
- **Someone else's published video** (YouTube creators, talks): keep the raw transcript in the scratch dir as working material. Hand over a detailed timestamped summary instead of the creator's full word-for-word text, and say that in one line.
- **"Transcribe this, then do what it shows"** (a how-to video): the transcript is the input to the real task. Read it fully, then check the claims against the live system and the official docs, because videos lag releases and show the presenter's models, not Mitch's. Build the setup with Mitch's own providers and models (see the `hermes-agent` skill's `references/model-routing.md` for Hermes setups).
- **"Transcribe this, then research / price / compare it"** (a build or product video): 
  1. Pull the video's own numbers out first (prices, per-unit vs total, benchmarks, with timestamps). Brief subagents with them.
  2. In the answer, show a reconciliation row: video figure -> scaled to Mitch's ask (e.g. 2 cards -> 4 cards) -> today's price. Only then add the extras the video skipped (PSU, host, boards). Say plainly where the video still holds. Why: bare ranges that don't line up with the video's headline number read as "you didn't watch it".
  3. Answer Mitch's stated goal (e.g. "bigger models and more KV cache"), framed as "what each option unlocks". If he says forks, drivers or hackiness don't matter, list them as setup notes, never as reasons not to buy.
  4. Lead with a one-line verdict, then one cost table and a numbered pick. Keep the agents' raw evidence out of the reply.
  5. For hardware builds, follow the `homelab-hardware-planning` skill for live host facts, deal-scout prices and simulation.
  6. Copy the video's key figures, with timestamps, into the thread's running notes file. The scratch transcript is pruned after 24 h idle, and later turns will need the figures again.

- **"Watch this, you'll get an idea" in the middle of a task** (the video illustrates what he wants from in-flight work): treat it as a requirements source for that task, not a summary request. Map each idea to Mitch's actual hardware or app with a vendor spec check (does his box have that slot/port/feature?) and a live occupancy check (`talosctl get pcidevices` on bare-metal nodes: a WLAN slot the spec lists as present already holds a Wi-Fi card, so a slot-based idea means swapping it out), answer with one table: idea (timestamp) | fits his setup? | payoff, plus a short skip list with reasons (things that failed in the video). Then feed the ideas that fit into the running child as a follow-up (see `claude-code` "Steer a running `-p` child") instead of only describing them.

- **"Transcribe this, then tell me what I can use across my repos"** (a tooling or workflow video):
  1. Inventory before you recommend. List what Hermes already has (`ls /opt/data/skills/*/`) and each repo's agent files (`AGENTS.md`, `.agents/skills`, `.claude/commands`). Repos live on GitHub `mitchross` and on Gitea `gitea.vanillax.me/vanillax` (mobichan-ng and news-reader), so check both before you say a repo doesn't exist.
  2. Clone the projects the video names into scratch, and read the real skill files, not only the video's description of them.
  3. Answer with one table: idea | repo | payoff. Then list what to skip and why, and end with one next step.
  4. When Mitch asks to install them, follow the `hermes-agent` skill's `references/skill-packs.md`.

## Pitfalls
- An `@url:` reference with a "no content extracted" warning still holds a valid link. Run the MeTube flow on it anyway.

- YouTube `HTTP 429` / "Sign in to confirm you're not a bot" in MeTube's `msg` means the home IP is rate-limited (TubeSync shares it and was paused for this). PO tokens alone don't fix it; it needs cookies.txt or a wait. Say so; other sites work. Mitch's VPN shares the home exit IP; once he turned the VPN off, the block cleared right away (2026-11-01). Ask him to try that first.
- OVMS (the Whisper server) accepts only mp3 and wav. Always convert with ffmpeg first.
- `curl -s` to LiteLLM succeeds even when Whisper is down, and the chunk JSON then holds `{"error":...}`. Grep the chunk files for `"error"` before you build the transcript, because otherwise you get timestamps with empty text. A Pending whisper pod (FailedScheduling, Insufficient memory) causes this.
- Leave files on the NAS alone; they are Mitch's.
- Open WebUI voice still uses its own CPU Whisper (browser webm mic input).
