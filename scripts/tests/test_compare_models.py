"""compare_models.py --baseline: a saved run shows beside a live one, against a mock OpenAI server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'benchmarks/ai-realworld-load/tools/compare_models.py'


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for chunk in ({'choices': [{'delta': {'content': f"answer from {body['model']}"}}]},
                      {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
                      {'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 4}}):
            self.wfile.write(f'data: {json.dumps(chunk)}\n\n'.encode())
        self.wfile.write(b'data: [DONE]\n\n')

    def log_message(self, format, *args):
        pass


class CompareBaselineTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1'
        self.tmp = Path(tempfile.mkdtemp())

    def run_compare(self, out, *extra):
        cmd = [sys.executable, str(SCRIPT), '--base-url', self.url, '--api-key', 'test', '--no-warmup',
               '--only', 'short-chat', '--out', str(self.tmp / out), *extra]
        return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ}, timeout=60)

    def test_saved_run_is_a_column_and_not_rerun(self):
        old = self.run_compare('old', '--models', 'qwen3.8-27b')
        self.assertEqual(old.returncode, 0, old.stderr)
        new = self.run_compare('new', '--models', 'qwen3.8-flash-next',
                               '--baseline', str(self.tmp / 'old/results.json'))
        self.assertEqual(new.returncode, 0, new.stderr)
        doc = json.loads((self.tmp / 'new/results.json').read_text())
        self.assertEqual([r['model'] for r in doc['results']], ['qwen3.8-flash-next'])
        self.assertEqual([r['model'] for r in doc['baseline_results']], ['qwen3.8-27b (baseline)'])
        self.assertEqual(set(doc['side_by_side']['short-chat']),
                         {'qwen3.8-27b (baseline)', 'qwen3.8-flash-next'})
        self.assertEqual(doc['meta']['baselines'][0]['problems'], [])
        md = (self.tmp / 'new/results.md').read_text()
        self.assertIn('| short-chat | qwen3.8-27b (baseline) |', md)
        self.assertIn('answer from qwen3.8-27b', md)

    def test_thinking_mismatch_is_refused(self):
        self.assertEqual(self.run_compare('old', '--models', 'qwen3.8-27b').returncode, 0)
        new = self.run_compare('new', '--models', 'x', '--thinking', 'medium',
                               '--baseline', str(self.tmp / 'old/results.json'))
        self.assertNotEqual(new.returncode, 0)
        self.assertIn('pass the same --thinking', new.stderr)


if __name__ == '__main__':
    unittest.main()
