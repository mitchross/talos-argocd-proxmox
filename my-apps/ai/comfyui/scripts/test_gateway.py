"""Verify bridge authentication without loading ComfyUI's GPU/image dependencies."""
import ast
import io
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request


def load_bridge(path):
    tree = ast.parse(path.read_text())
    parts = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"_chat_completion", "_strip_thinking"}]
    namespace = {"json": json, "os": os, "re": re, "urllib": urllib,
                 "_DEFAULT_SERVER": "http://litellm-service.litellm.svc.cluster.local:4000"}
    exec(compile(ast.Module(body=parts, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_chat_completion"]


class GatewayTests(unittest.TestCase):
    def test_both_bridge_copies_authenticate_and_normalize_saved_urls(self):
        root = Path(__file__).resolve().parents[1]
        for path in [root / "image_to_llamacpp_base64.py", root / "custom-nodes/image_to_llamacpp_base64.py"]:
            complete = load_bridge(path)
            for endpoint in ["http://llama-cpp-service.llama-cpp.svc.cluster.local:8080", "http://vllm-service.vllm.svc.cluster.local:8080", "http://litellm-service.litellm.svc.cluster.local:4000"]:
                captured = []
                def respond(request, **kwargs):
                    captured.append(request)
                    return io.BytesIO(b'{"choices":[{"message":{"content":"caption"}}]}')
                with patch.dict(os.environ, {"LITELLM_API_KEY": "synthetic-key"}), patch.object(urllib.request, "urlopen", respond):
                    self.assertEqual(complete(endpoint, "qwen3.8-27b", [], 0.6, 1024), "caption")
                self.assertEqual(captured[0].full_url, "http://litellm-service.litellm.svc.cluster.local:4000/v1/chat/completions")
                self.assertEqual(captured[0].get_header("Authorization"), "Bearer synthetic-key")
                self.assertEqual(json.loads(captured[0].data)["metadata"]["tags"], ["comfyui"])

    def test_arbitrary_endpoint_cannot_receive_gateway_secret(self):
        complete = load_bridge(Path(__file__).resolve().parents[1] / "image_to_llamacpp_base64.py")
        with patch.dict(os.environ, {"LITELLM_API_KEY": "synthetic-key"}), patch.object(urllib.request, "urlopen") as request:
            with self.assertRaises(ValueError):
                complete("https://untrusted.example", "qwen3.8-27b", [], 0.6, 1024)
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
