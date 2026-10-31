#!/usr/bin/env python3
"""Watch the media inbox and write a Markdown transcript next to every new video or audio file.

For each media file without a sibling `<name>.md`:
  1. wait until the file has stopped changing (SMB copies arrive slowly),
  2. ffmpeg -> 16 kHz mono mp3 chunks (OVMS accepts only mp3/wav),
  3. POST each chunk to LiteLLM /v1/audio/transcriptions (model `whisper`),
  4. write `<name>.md` atomically.
A bad file writes `<name>.transcribe-error.txt` (delete it to retry); a down backend is retried next pass.
Standard library only.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

INBOX = Path(os.environ.get("INBOX_DIR", "/inbox"))
API_BASE = os.environ.get("LITELLM_BASE_URL", "http://litellm-service.litellm.svc.cluster.local:4000/v1").rstrip("/")
API_KEY = os.environ.get("LITELLM_API_KEY", "")
MODEL = os.environ.get("STT_MODEL", "whisper")
LANGUAGE = os.environ.get("STT_LANGUAGE", "")  # empty = let Whisper detect
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "60"))
SETTLE_SECONDS = int(os.environ.get("SETTLE_SECONDS", "120"))
CHUNK_SECONDS = int(os.environ.get("CHUNK_SECONDS", "600"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "1800"))
WORK_DIR = os.environ.get("WORK_DIR") or None

MEDIA_EXTS = {
    ".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".ts", ".flv",
    ".mp3", ".m4a", ".wav", ".opus", ".ogg", ".flac", ".aac",
}
ERROR_SUFFIX = ".transcribe-error.txt"

log = logging.getLogger("transcriber")


class Transient(Exception):
    """Backend down or busy: retry the file next pass instead of marking it failed."""


def transcript_path(media: Path) -> Path:
    return media.with_suffix(".md")


def error_path(media: Path) -> Path:
    return media.with_name(media.stem + ERROR_SUFFIX)


def find_pending(root: Path, now: float) -> list[Path]:
    """Media files with no transcript, no error marker, unchanged for SETTLE_SECONDS. Oldest first."""
    pending = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden/system folders: MeTube state, Synology @eaDir, macOS junk.
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "@", "#"))]
        for name in filenames:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            if p.suffix.lower() not in MEDIA_EXTS:
                continue
            if transcript_path(p).exists() or error_path(p).exists():
                continue
            try:
                mtime = p.stat().st_mtime
            except FileNotFoundError:
                continue
            if now - mtime < SETTLE_SECONDS:
                continue
            pending.append((mtime, p))
    return [p for _, p in sorted(pending)]


def probe_duration(media: Path) -> float | None:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def split_audio(media: Path, out_dir: Path) -> list[Path]:
    """Extract audio as 16 kHz mono mp3, cut into CHUNK_SECONDS pieces."""
    pattern = out_dir / "chunk%04d.mp3"
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(media),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k",
        "-f", "segment", "-segment_time", str(CHUNK_SECONDS), "-reset_timestamps", "1",
        str(pattern),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {res.stderr.strip()[-500:]}")
    chunks = sorted(out_dir.glob("chunk*.mp3"))
    if not chunks:
        raise RuntimeError("ffmpeg produced no audio (file has no audio track?)")
    return chunks


def multipart(fields: list[tuple[str, str]], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n".encode()
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def transcribe_chunk(chunk: Path) -> dict:
    fields = [("model", MODEL), ("response_format", "verbose_json"), ("timestamp_granularities[]", "segment")]
    if LANGUAGE:
        fields.append(("language", LANGUAGE))
    body, ctype = multipart(fields, "file", chunk)
    req = urllib.request.Request(
        f"{API_BASE}/audio/transcriptions", data=body, method="POST",
        headers={"Content-Type": ctype, "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code} from {API_BASE}: {e.read().decode(errors='replace')[:500]}"
        raise (Transient if e.code == 429 or e.code >= 500 else RuntimeError)(msg) from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise Transient(f"{API_BASE} unreachable: {e}") from e


def stamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def render_markdown(media: Path, duration: float | None, results: list[dict], elapsed: float) -> str:
    lines = [f"# {media.stem}", ""]
    lines.append(f"- Source: `{media.name}`")
    if duration:
        lines.append(f"- Length: {stamp(duration)}")
    lines.append(f"- Transcribed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} in {elapsed:.0f}s by `{MODEL}`")
    lines += ["", "## Transcript", ""]
    for i, r in enumerate(results):
        offset = i * CHUNK_SECONDS
        segments = r.get("segments") or []
        if segments:
            for seg in segments:
                text = (seg.get("text") or "").strip()
                if text:
                    lines.append(f"[{stamp(offset + float(seg.get('start') or 0))}] {text}")
        else:
            text = (r.get("text") or "").strip()
            if text:
                lines.append(f"[{stamp(offset)}] {text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_atomic(path: Path, text: str) -> None:
    # Hidden temp name so the scanner and SMB clients ignore it until the rename.
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def process(media: Path) -> None:
    started = time.monotonic()
    log.info("transcribing %s", media)
    duration = probe_duration(media)
    work = Path(tempfile.mkdtemp(prefix="stt-", dir=WORK_DIR))
    try:
        chunks = split_audio(media, work)
        results = []
        for n, chunk in enumerate(chunks, 1):
            log.info("  chunk %d/%d", n, len(chunks))
            results.append(transcribe_chunk(chunk))
        md = render_markdown(media, duration, results, time.monotonic() - started)
        write_atomic(transcript_path(media), md)
        log.info("wrote %s (%.0fs)", transcript_path(media), time.monotonic() - started)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_once() -> int:
    done = 0
    for media in find_pending(INBOX, time.time()):
        try:
            process(media)
            done += 1
        except Transient as e:
            log.warning("backend unavailable, retrying next pass: %s", e)
            break
        except Exception as e:  # one bad file must not stop the loop
            log.error("failed %s: %s", media, e)
            try:
                write_atomic(error_path(media), f"{datetime.now(timezone.utc).isoformat()}\n{e}\n\nDelete this file to retry.\n")
            except OSError as werr:
                log.error("could not write error marker for %s: %s", media, werr)
    return done


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    if not API_KEY:
        sys.exit("LITELLM_API_KEY is not set")
    if not INBOX.is_dir():
        sys.exit(f"inbox {INBOX} does not exist")
    log.info("watching %s every %ss via %s model=%s", INBOX, POLL_SECONDS, API_BASE, MODEL)
    while True:
        run_once()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
