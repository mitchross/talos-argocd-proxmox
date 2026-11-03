"""Exercise cache readiness against missing, corrupt and interrupted artifacts."""
import hashlib
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'my-apps/ai/vllm/scripts/model_cache.py'


class ModelCacheTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'The verified model-cache implementation is missing')
        spec = importlib.util.spec_from_file_location('model_cache', SCRIPT)
        self.cache = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cache)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.archive = self.root / 'archive'
        self.local = self.root / 'local'
        self.payloads = {'config.json': b'{"model_type":"qwen3_5"}', 'model.safetensors': b'valid test weights'}
        files = []
        for name, data in self.payloads.items():
            (self.source / name).write_bytes(data)
            files.append({'name': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        manifest = {'repo': 'Qwen/test', 'revision': 'abc123', 'directory': 'Qwen-test-abc123', 'files': files}
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps(manifest))
        self.model = self.cache.ModelCache(self.manifest)

    def download(self):
        self.model.download(self.archive, self.source.as_uri())

    def test_complete_download_and_sync_publish_readiness(self):
        self.download()
        self.model.sync(self.archive, self.local)
        self.assertTrue(self.model.ready(self.local))
        self.assertEqual((self.local / self.model.directory / 'model.safetensors').read_bytes(), b'valid test weights')

    def test_same_size_corruption_is_repaired_before_readiness(self):
        self.download()
        self.model.sync(self.archive, self.local)
        target = self.local / self.model.directory / 'model.safetensors'
        target.write_bytes(b'x' * len(b'valid test weights'))
        self.model.sync(self.archive, self.local)
        self.assertEqual(target.read_bytes(), b'valid test weights')
        self.assertTrue(self.model.ready(self.local))

    def test_corrupt_source_invalidates_existing_ready_marker(self):
        self.download()
        self.model.sync(self.archive, self.local)
        (self.archive / self.model.directory / 'model.safetensors').write_bytes(b'x' * len(b'valid test weights'))
        with self.assertRaises(ValueError):
            self.model.sync(self.archive, self.local)
        self.assertFalse(self.model.ready(self.local))

    def test_missing_shard_never_publishes_ready(self):
        self.download()
        (self.archive / self.model.directory / 'model.safetensors').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.model.sync(self.archive, self.local)
        self.assertFalse(self.model.ready(self.local))

    def test_wrong_download_hash_never_publishes_complete(self):
        (self.source / 'model.safetensors').write_bytes(b'incorrect weights')
        with self.assertRaises(ValueError):
            self.download()
        self.assertFalse(self.model.ready(self.archive))

    def test_partial_transfer_can_restart_when_source_ignores_range(self):
        directory = self.archive / self.model.directory
        directory.mkdir(parents=True)
        (directory / 'model.safetensors.part').write_bytes(b'bad prefix')
        self.download()
        self.assertTrue(self.model.ready(self.archive))
        self.assertEqual((directory / 'model.safetensors').read_bytes(), b'valid test weights')

    def http_source(self, wrong_offset=False):
        payloads = self.payloads
        ranges = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data = payloads[self.path.lstrip('/')]
                requested = self.headers.get('Range')
                ranges.append(requested)
                offset = int(requested.split('=')[1].split('-')[0]) if requested else 0
                self.send_response(206 if requested else 200)
                if requested:
                    start = offset + 1 if wrong_offset else offset
                    self.send_header('Content-Range', f'bytes {start}-{len(data)-1}/{len(data)}')
                self.send_header('Content-Length', str(len(data) - offset))
                self.end_headers()
                self.wfile.write(data[offset:])

            def log_message(self, *args):
                pass

        # The local test server must not depend on workstation reverse DNS.
        with patch('socket.getfqdn', return_value='localhost'):
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}', ranges

    def test_http_partial_transfer_resumes_and_verifies(self):
        directory = self.archive / self.model.directory
        directory.mkdir(parents=True)
        (directory / 'model.safetensors.part').write_bytes(b'valid')
        url, ranges = self.http_source()
        self.model.download(self.archive, url)
        self.assertIn('bytes=5-', ranges)
        self.assertTrue(self.model.ready(self.archive))
        self.assertEqual((directory / 'model.safetensors').read_bytes(), b'valid test weights')

    def test_http_wrong_resume_offset_never_publishes_ready(self):
        directory = self.archive / self.model.directory
        directory.mkdir(parents=True)
        (directory / 'model.safetensors.part').write_bytes(b'valid')
        url, _ = self.http_source(wrong_offset=True)
        with self.assertRaisesRegex(ValueError, 'wrong byte offset'):
            self.model.download(self.archive, url)
        self.assertFalse(self.model.ready(self.archive))
        self.assertFalse((directory / 'model.safetensors').exists())

    def test_changed_manifest_invalidates_old_readiness(self):
        self.download()
        d = json.loads(self.manifest.read_text())
        d['revision'] = 'def456'
        self.manifest.write_text(json.dumps(d))
        self.assertFalse(self.cache.ModelCache(self.manifest).ready(self.archive))


if __name__ == '__main__':
    unittest.main()
