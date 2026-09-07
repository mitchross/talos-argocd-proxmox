"""Add LiteLLM Bearer authentication to the pinned application's LLM requests."""

import hashlib
from pathlib import Path

SOURCE = '/app/app.py'
EXPECTED_SHA256 = '996029d773f752d837cbe7bc22c3adc460ee46c835ab3af8bb19e75baa8fa42b'
OLD = 'DIGEST_LLM_URL, data=body, headers={"content-type": "application/json"})'
NEW = 'DIGEST_LLM_URL, data=body, headers={"content-type": "application/json", "Authorization": "Bearer " + os.environ["LITELLM_API_KEY"]})'
COUNT = 1


def patch_source(source):
    if hashlib.sha256(source.encode()).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("Pinned application source changed; review LiteLLM authentication overlay")
    if source.count(OLD) != COUNT:
        raise RuntimeError("LLM call sites changed; review LiteLLM authentication overlay")
    return source.replace(OLD, NEW)


if __name__ == "__main__":
    Path("/patched/" + Path(SOURCE).name).write_text(patch_source(Path(SOURCE).read_text()))
    print("Prepared authenticated LiteLLM call sites")
