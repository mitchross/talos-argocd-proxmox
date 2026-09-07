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
import urllib.request
DIGEST_LLM_URL = "http://litellm-service.litellm.svc.cluster.local:4000/v1/chat/completions"
def request():
    body = b'{"model":"qwen3.8-27b","temperature":0.2,"max_tokens":400}'
    return urllib.request.Request(
        DIGEST_LLM_URL, data=body, headers={"content-type": "application/json"})
'''


class LiteLLMAuthTests(unittest.TestCase):
    def prepared(self):
        with patch.object(overlay, "EXPECTED_SHA256", hashlib.sha256(SOURCE.encode()).hexdigest()):
            return overlay.patch_source(SOURCE)

    def test_real_request_gains_auth_without_changing_body_or_destination(self):
        before, after = {}, {}
        exec(SOURCE, before)
        exec(self.prepared(), after)
        with patch.dict(os.environ, {"LITELLM_API_KEY": "unit-test-key"}):
            original = before["request"]()
            authenticated = after["request"]()
        self.assertIsNone(original.get_header("Authorization"))
        self.assertEqual(authenticated.get_header("Authorization"), "Bearer unit-test-key")
        self.assertEqual(authenticated.full_url, original.full_url)
        self.assertEqual(authenticated.data, original.data)
        self.assertEqual(authenticated.get_header("Content-type"), "application/json")

    def test_absent_key_fails_instead_of_sending_anonymous_request(self):
        namespace = {}
        exec(self.prepared(), namespace)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(KeyError):
            namespace["request"]()

    def test_source_drift_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            overlay.patch_source(SOURCE)


if __name__ == "__main__":
    unittest.main()
