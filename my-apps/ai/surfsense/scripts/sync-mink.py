"""Import Git-backed Mink Markdown through SurfSense 0.0.39's folder API."""

import base64
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import httpx


def collect_notes(repo: Path, include: str) -> list[Path]:
    files = set()
    for directory in include.split(","):
        relative = Path(directory.strip())
        if not relative.parts or relative.is_absolute() or any(
            part.startswith(".") for part in relative.parts
        ):
            raise ValueError("INCLUDE_DIRS must contain visible relative directories")
        base = repo / relative
        if not base.is_dir() or any(p.is_symlink() for p in [base, *base.parents] if p != repo):
            raise ValueError(f"Missing or symlinked include directory: {relative}")
        for path in base.rglob("*.md"):
            parts = path.relative_to(repo).parts
            if any(part.startswith(".") for part in parts):
                continue
            if any(p.is_symlink() for p in [path, *path.parents] if p != repo):
                continue
            if path.is_file():
                if len(parts) > 8:
                    raise ValueError("Note exceeds SurfSense's eight-level folder limit")
                files.add(path)
    if not files:
        raise ValueError("No Markdown notes found; refusing an empty import")
    return sorted(files)


def clone_repo(destination: Path, repository: str, branch: str, token: str) -> None:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("SOURCE_REPO must be a GitHub owner/repository")
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}",
    })
    result = subprocess.run(
        ["git", "clone", "--quiet", "--depth=1", "--single-branch",
         "--branch", branch, "--", f"https://github.com/{repository}.git", str(destination)],
        env=env, capture_output=True, timeout=300,
    )
    if result.returncode:
        raise RuntimeError("Git clone failed; check repository, branch, and read token")


def get_json(client: httpx.Client, path: str, **kwargs):
    for attempt in range(4):
        try:
            response = client.get(path, **kwargs)
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response.json()
        except httpx.TransportError:
            if attempt == 3:
                raise
        if attempt < 3:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"SurfSense read failed after retries: {path}")


def upload_logs(client: httpx.Client, workspace: int) -> list[dict]:
    return get_json(client, "/api/v1/logs", params={
        "workspace_id": workspace, "source": "uploaded_folder_indexing", "limit": 100,
    })


def wait_for_batch(client: httpx.Client, workspace: int, previous_id: int,
                   count: int, timeout: float, poll: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        logs = [entry for entry in upload_logs(client, workspace) if entry["id"] > previous_id]
        if len(logs) > 1:
            raise RuntimeError("Concurrent folder uploads detected; cannot identify this batch")
        if logs:
            entry = logs[0]
            if (entry.get("log_metadata") or {}).get("file_count") != count:
                raise RuntimeError("Worker log does not match the uploaded batch")
            if entry["status"] == "FAILED":
                raise RuntimeError(f"SurfSense worker failed; inspect log {entry['id']}")
            if entry["status"] == "SUCCESS":
                # 0.0.39 can report SUCCESS with failed files; counters are in its message.
                match = re.fullmatch(r"Upload indexing complete: (\d+) indexed, (\d+) failed", entry["message"])
                if not match or int(match[2]):
                    raise RuntimeError(f"SurfSense reported indexing errors; inspect log {entry['id']}")
                print(f"Worker completed batch: {match[1]} indexed, remaining files unchanged", flush=True)
                return
        time.sleep(poll)
    raise RuntimeError("Timed out waiting for the worker to complete the uploaded batch")


def sync_notes(client: httpx.Client, repo: Path, files: list[Path], workspace: int,
               folder: str, batch_size: int, timeout: float) -> None:
    if not 1 <= batch_size <= 500:
        raise ValueError("BATCH_SIZE must be between 1 and 500")
    folders = get_json(client, "/api/v1/folders", params={"workspace_id": workspace})
    roots = [f for f in folders if f["name"] == folder and f["parent_id"] is None]
    if len(roots) > 1:
        raise RuntimeError("Multiple Mink root folders found")
    root_id = roots[0]["id"] if roots else None
    for offset in range(0, len(files), batch_size):
        previous = upload_logs(client, workspace)
        if any(entry["status"] == "IN_PROGRESS" for entry in previous):
            raise RuntimeError("A folder upload is still running; wait for it before syncing")
        previous_id = max((entry["id"] for entry in previous), default=0)
        batch = files[offset:offset + batch_size]
        relative = [p.relative_to(repo).as_posix() for p in batch]
        data = {
            "folder_name": folder, "workspace_id": str(workspace),
            "relative_paths": json.dumps(relative), "processing_mode": "basic",
        }
        if root_id is not None:
            data["root_folder_id"] = str(root_id)
        with ExitStack() as stack:
            multipart = [("files", (name, stack.enter_context(path.open("rb")), "text/markdown"))
                         for name, path in zip(relative, batch)]
            # Never retry an ambiguous POST: it may already have queued a worker task.
            response = client.post("/api/v1/documents/folder-upload", data=data, files=multipart)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("root_folder_id"), int) or body.get("file_count") != len(batch):
            raise RuntimeError("Unexpected folder-upload response")
        if root_id is not None and body["root_folder_id"] != root_id:
            raise RuntimeError("SurfSense returned a different root folder")
        root_id = body["root_folder_id"]
        print(f"Accepted {offset + len(batch)}/{len(files)} notes; waiting for worker", flush=True)
        wait_for_batch(client, workspace, previous_id, len(batch), timeout)
    print(f"Mink import complete: {len(files)} notes processed in folder {root_id}", flush=True)


def main() -> None:
    token = os.environ["SURFSENSE_TOKEN"]
    if not token.startswith("ss_pat_"):
        raise ValueError("SURFSENSE_TOKEN must be a SurfSense personal access token")
    work = Path(os.environ.get("WORKDIR", "/work"))
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mink-", dir=work) as scratch:
        repo = Path(scratch) / "repo"
        clone_repo(repo, os.environ["SOURCE_REPO"], os.environ.get("SOURCE_BRANCH", "main"),
                   os.environ["GITHUB_PAT"])
        files = collect_notes(repo, os.environ.get("INCLUDE_DIRS", "wiki"))
        print(f"Selected {len(files)} Markdown notes", flush=True)
        with httpx.Client(
            base_url=os.environ["SURFSENSE_API"].rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(600, connect=10), follow_redirects=False,
        ) as client:
            sync_notes(client, repo, files, int(os.environ["WORKSPACE_ID"]),
                       os.environ.get("FOLDER_NAME", "Mink"),
                       int(os.environ.get("BATCH_SIZE", "500")),
                       float(os.environ.get("INDEX_TIMEOUT_SECONDS", "5400")))


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, subprocess.TimeoutExpired) as error:
        # Avoid response bodies and subprocess output, which may contain notes or credentials.
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else type(error).__name__
        sys.exit(f"Mink sync failed: {status}; inspect SurfSense task logs or Git access")
    except (KeyError, ValueError, RuntimeError) as error:
        sys.exit(f"Mink sync failed: {error}")
