"""Exercise the downloader's publication and preservation contract."""
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'my-apps/knowledge/kiwix/scripts/download-library.sh'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class LibraryDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.origin = self.root / 'origin'
        self.origin.mkdir()
        self.data = self.root / 'data'
        self.data.mkdir()
        self.payload = b'offline-library-test\n' * 100
        (self.origin / 'reference.zim').write_bytes(self.payload)
        handler = functools.partial(QuietHandler, directory=str(self.origin))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}/reference.zim'
        self.manifest = self.root / 'collections.tsv'
        self.checksum = hashlib.sha256(self.payload).hexdigest()

    def run_download(self, checksum=None):
        self.manifest.write_text(f'# SHA256 bytes URL\n{checksum or self.checksum}\t{len(self.payload)}\t{self.url}\n')
        env = {**os.environ, 'DATA_DIR': str(self.data), 'MANIFEST': str(self.manifest), 'RETRY_DELAY': '0'}
        return subprocess.run(['sh', str(SCRIPT)], env=env, capture_output=True, text=True, timeout=10)

    def test_verified_download_and_idempotent_retry(self):
        result = self.run_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.data / 'reference.zim'
        self.assertEqual(target.read_bytes(), self.payload)
        before = target.stat().st_mtime_ns
        (self.origin / 'reference.zim').unlink()
        result = self.run_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertIn('Already verified', result.stdout)

    def test_bad_checksum_never_publishes_archive(self):
        result = self.run_download('0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.data / 'reference.zim').exists())
        self.assertFalse((self.data / '.downloads/reference.zim.part').exists())

    def test_existing_different_archive_is_preserved(self):
        target = self.data / 'reference.zim'
        target.write_bytes(b'existing library content')
        result = self.run_download()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), b'existing library content')

    def test_existing_valid_archive_is_adopted_without_download(self):
        (self.data / 'reference.zim').write_bytes(self.payload)
        (self.origin / 'reference.zim').unlink()
        result = self.run_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.data / '.downloads/reference.zim.sha256').read_text().strip(), self.checksum)

    def test_partial_download_is_completed_before_publication(self):
        partial = self.data / '.downloads/reference.zim.part'
        partial.parent.mkdir()
        partial.write_bytes(self.payload[:100])
        result = self.run_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.data / 'reference.zim').read_bytes(), self.payload)
        self.assertFalse(partial.exists())


if __name__ == '__main__':
    unittest.main()
