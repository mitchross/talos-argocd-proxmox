import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

spec = importlib.util.spec_from_file_location("sync_mink", Path(__file__).with_name("sync-mink.py"))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def worker_log(status="SUCCESS", failed=0):
    return {"id": 2, "status": status, "log_metadata": {"file_count": 1},
            "message": f"Upload indexing complete: 1 indexed, {failed} failed"}


class MinkSyncTests(unittest.TestCase):
    def test_selection_excludes_hidden_and_symlinked_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "wiki/.hidden").mkdir(parents=True)
            (repo / "wiki/note.md").write_text("note")
            (repo / "wiki/.hidden/token.md").write_text("secret")
            (repo / "outside.md").write_text("outside")
            (repo / "wiki/link.md").symlink_to(repo / "outside.md")
            self.assertEqual(sync.collect_notes(repo, "wiki"), [repo / "wiki/note.md"])
            for include in ("../", "/tmp", "missing", ""):
                with self.assertRaises(ValueError):
                    sync.collect_notes(repo, include)

    @patch.object(sync.time, "sleep")
    def test_waits_for_worker_start_and_finish(self, sleep):
        with patch.object(sync, "upload_logs", side_effect=[[], [worker_log("IN_PROGRESS")], [worker_log()]]):
            sync.wait_for_batch(None, 1, 1, 1, 10)
        self.assertEqual(sleep.call_count, 2)

    def test_partial_failure_is_not_success(self):
        with patch.object(sync, "upload_logs", return_value=[worker_log(failed=1)]):
            with self.assertRaisesRegex(RuntimeError, "indexing errors"):
                sync.wait_for_batch(None, 1, 1, 1, 10)

    def test_concurrent_upload_is_rejected(self):
        with patch.object(sync, "upload_logs", return_value=[worker_log(), {**worker_log(), "id": 3}]):
            with self.assertRaisesRegex(RuntimeError, "Concurrent"):
                sync.wait_for_batch(None, 1, 1, 1, 10)

    def test_batch_timeout(self):
        with patch.object(sync, "upload_logs", return_value=[]), patch.object(sync.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(RuntimeError, "Timed out"):
                sync.wait_for_batch(None, 1, 1, 1, 10)

    def test_upload_waits_for_every_batch_and_reuses_root(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/v1/folders":
                return httpx.Response(200, json=[{"name": "Mink", "id": 7, "parent_id": None}])
            self.assertEqual(request.method, "POST")
            self.assertIn(b'name="root_folder_id"\r\n\r\n7', request.content)
            return httpx.Response(200, json={"root_folder_id": 7, "file_count": 1})

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            files = [repo / "a.md", repo / "b.md"]
            for file in files:
                file.write_text("Markdown")
            with httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)) as client:
                with patch.object(sync, "upload_logs", return_value=[]), patch.object(sync, "wait_for_batch") as wait:
                    sync.sync_notes(client, repo, files, 1, "Mink", 1, 10)
                    self.assertEqual(wait.call_count, 2)
            self.assertEqual(len(requests), 3)

    def test_ambiguous_post_is_not_retried(self):
        posts = []

        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json=[])
            posts.append(request)
            raise httpx.ReadTimeout("ambiguous upload")

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            file = repo / "a.md"
            file.write_text("Markdown")
            with httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(httpx.ReadTimeout):
                    sync.sync_notes(client, repo, [file], 1, "Mink", 1, 10)
            self.assertEqual(len(posts), 1)


if __name__ == "__main__":
    unittest.main()
