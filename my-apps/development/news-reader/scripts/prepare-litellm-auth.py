"""Add LiteLLM Bearer authentication to the pinned application's LLM requests."""

import hashlib
from pathlib import Path

SOURCE = '/app/worker.py'
EXPECTED_SHA256 = '80f6096bc6110229e0fca022baa90a75c6552623bd4bb03bf5b15665abb2e831'
OLD = 'client.post(LLM_URL, json={'
NEW = 'client.post(LLM_URL, headers={"Authorization": "Bearer " + os.environ["LITELLM_API_KEY"]}, json={'
COUNT = 2


def patch_source(source):
    if hashlib.sha256(source.encode()).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("Pinned application source changed; review LiteLLM authentication overlay")
    if source.count(OLD) != COUNT:
        raise RuntimeError("LLM call sites changed; review LiteLLM authentication overlay")
    return source.replace(OLD, NEW)


if __name__ == "__main__":
    Path("/patched/" + Path(SOURCE).name).write_text(patch_source(Path(SOURCE).read_text()))
    print("Prepared authenticated LiteLLM call sites")
