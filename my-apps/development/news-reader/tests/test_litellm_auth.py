import asyncio
import hashlib
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("overlay", Path(__file__).resolve().parents[1] / "scripts/prepare-litellm-auth.py")
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)

SOURCE = '''import os
LLM_URL = "http://litellm-service.litellm.svc.cluster.local:4000/v1/chat/completions"
async def summarize(client):
    return await client.post(LLM_URL, json={"model": "qwen3.8-27b", "temperature": 0.3, "max_tokens": 512})
async def headline(client):
    return await client.post(LLM_URL, json={"model": "qwen3.8-27b", "temperature": 0.7, "max_tokens": 100})
'''


class RecordingClient:
    async def post(self, url, **kwargs):
        return {"url": url, **kwargs}


class LiteLLMAuthTests(unittest.TestCase):
    def prepared(self):
        with patch.object(overlay, "EXPECTED_SHA256", hashlib.sha256(SOURCE.encode()).hexdigest()):
            return overlay.patch_source(SOURCE)

    def test_both_request_paths_gain_auth_and_keep_their_payload(self):
        before, after = {}, {}
        exec(SOURCE, before)
        exec(self.prepared(), after)
        with patch.dict(os.environ, {"LITELLM_API_KEY": "unit-test-key"}):
            for function in ("summarize", "headline"):
                original = asyncio.run(before[function](RecordingClient()))
                authenticated = asyncio.run(after[function](RecordingClient()))
                self.assertNotIn("headers", original)
                self.assertEqual(authenticated.pop("headers"), {"Authorization": "Bearer unit-test-key"})
                self.assertEqual(authenticated, original)

    def test_absent_key_fails_before_request(self):
        namespace = {}
        exec(self.prepared(), namespace)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(KeyError):
            asyncio.run(namespace["summarize"](RecordingClient()))

    def test_source_drift_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            overlay.patch_source(SOURCE)


if __name__ == "__main__":
    unittest.main()
