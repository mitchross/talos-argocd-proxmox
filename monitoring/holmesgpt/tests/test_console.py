import importlib.util
import json
from pathlib import Path
import threading
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SPEC = importlib.util.spec_from_file_location("console", Path(__file__).parents[1] / "scripts/server.py")
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)


class ManagerTest(unittest.TestCase):
    def test_concurrent_submission_rejected(self):
        gate = threading.Event()
        manager = console.Investigations(lambda *_: (gate.wait(2), {"analysis": "ok", "evidence": []})[1])
        first = manager.submit("why", "test", "15m")
        self.assertIsNotNone(first)
        self.assertIsNone(manager.submit("again", "test", "15m"))
        gate.set()
        manager.pool.shutdown(wait=True)
        self.assertEqual(manager.get(first)["state"], "complete")
        self.assertFalse(manager.busy)

    def test_network_timeout_fails_closed(self):
        def fail(*_):
            raise URLError("timeout")
        manager = console.Investigations(fail)
        first = manager.submit("why", "test", "15m")
        manager.pool.shutdown(wait=True)
        self.assertEqual(manager.get(first)["state"], "failed")
        self.assertTrue(manager.uncertain)
        self.assertIsNone(manager.submit("retry", "test", "15m"))

    def test_expired_results_disappear(self):
        manager = console.Investigations()
        manager.jobs["old"] = {"created": time.time() - 1000}
        self.assertIsNone(manager.get("old"))
        manager.pool.shutdown()


class HTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = console.Investigations(lambda *_: {"analysis": "mock evidence", "evidence": []})
        cls.server = console.ConsoleServer(("127.0.0.1", 0), cls.manager)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.manager.pool.shutdown(wait=True)
        cls.thread.join()

    def post(self, data, **headers):
        defaults = {"Host": "localhost:8080", "Origin": "http://localhost:8080", "Content-Type": "application/json", "X-CSRF-Token": self.server.csrf}
        defaults.update(headers)
        request = Request(self.url + "/api/investigate", data=json.dumps(data).encode(), headers=defaults, method="POST")
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_valid_question(self):
        code, result = self.post({"question": "why", "namespace": "test", "window": "15m"})
        self.assertEqual(code, 202)
        self.assertEqual(len(result["id"]), 32)

    def test_cross_origin_rejected(self):
        self.assertEqual(self.post({"question": "why"}, Origin="https://evil.example")[0], 403)

    def test_csrf_required(self):
        self.assertEqual(self.post({"question": "why"}, **{"X-CSRF-Token": "wrong"})[0], 403)

    def test_rebinding_host_rejected(self):
        self.assertEqual(self.post({"question": "why"}, Host="evil.example")[0], 403)

    def test_invalid_namespace(self):
        self.assertEqual(self.post({"question": "why", "namespace": "x;curl evil"})[0], 400)

    def test_invalid_window(self):
        self.assertEqual(self.post({"question": "why", "window": "1y"})[0], 400)

    def test_non_object_and_large_question(self):
        self.assertEqual(self.post([])[0], 400)
        self.assertEqual(self.post({"question": "x" * 2001})[0], 400)
        self.assertEqual(self.post({"question": "x" * 10000})[0], 413)

    def test_unknown_path_is_not_a_proxy(self):
        request = Request(self.url + "/api/chat", headers={"Host": "localhost:8080"})
        with self.assertRaises(HTTPError) as context:
            urlopen(request)
        self.assertEqual(context.exception.code, 404)

    def test_static_page_and_security_headers(self):
        request = Request(self.url + "/", headers={"Host": "localhost:8080"})
        with urlopen(request, timeout=3) as response:
            self.assertIn("Ask the cluster", response.read().decode())
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_same_origin_session(self):
        request = Request(self.url + "/api/session", headers={"Host": "localhost:8080"})
        with urlopen(request, timeout=3) as response:
            self.assertEqual(json.load(response)["csrf"], self.server.csrf)

    def test_no_unsafe_html_sink(self):
        javascript = (Path(__file__).parents[1] / "ui/app.js").read_text()
        self.assertNotIn("innerHTML", javascript)
        self.assertNotIn("localStorage", javascript)
        self.assertNotIn("sessionStorage", javascript)


if __name__ == "__main__":
    unittest.main()
