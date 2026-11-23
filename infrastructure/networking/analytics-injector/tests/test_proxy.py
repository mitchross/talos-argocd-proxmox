"""Run with python3 -m unittest discover -s infrastructure/networking/analytics-injector/tests -v.

Requires Docker, openssl, and the python:3.13-alpine fixture image.
Exercises the deployed nginx config against a TLS origin with the pod's restrictions.
"""

import gzip
import http.client
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import unittest
import uuid


APP = Path(__file__).resolve().parents[1]
MARKER = b"Umami (injected in-cluster)"
HTML = b"<html><head><title>origin</title></head><body>hello</body></html>"
ORIGIN = r'''
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
import time

HTML = b"<html><head><title>origin</title></head><body>hello</body></html>"

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args):
        pass
    def do_GET(self):
        if self.path == "/ws":
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.end_headers()
            self.wfile.write(self.rfile.read(4))
            self.wfile.flush()
            self.close_connection = True
            return
        status = {"/redirect": 302, "/error": 500, "/empty": 204,
                  "/not-modified": 304}.get(self.path, 200)
        body = HTML
        ctype = "application/json" if self.path == "/json" else "text/html; charset=utf-8"
        if self.path == "/stream":
            body = b"data: first\n\ndata: second\n\n"
            ctype = "text/event-stream"
        elif self.path == "/upper":
            body = HTML.replace(b"</head>", b"</HEAD>")
        if status in (204, 304):
            body = b""
        compressed = "gzip" in self.headers.get("Accept-Encoding", "") and self.path != "/stream"
        if self.path == "/anubis":
            self.send_header_later = ["session=abc; Path=/",
                                      "techaro.lol-anubis-cookie-verification=chall-1; Path=/"]
        elif self.path == "/anubis-cleared":
            self.send_header_later = ["techaro.lol-anubis-cookie-verification=; Path=/; Max-Age=0"]
        else:
            self.send_header_later = []
        compressed = compressed and bool(body)
        if compressed:
            body = gzip.compress(body)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("ETag", '"origin"')
        self.send_header("Content-Security-Policy", "default-src 'self'")
        self.send_header("Last-Modified", "Tue, 29 Sep 2026 12:00:00 GMT")
        self.send_header("X-Origin-Host", self.headers.get("Host", ""))
        self.send_header("X-Origin-SNI", getattr(self.connection, "sni", ""))
        self.send_header("X-Origin-URI", self.path)
        for cookie in self.send_header_later:
            self.send_header("Set-Cookie", cookie)
        for name in ("Authorization", "CF-Connecting-IP", "X-Forwarded-For", "Accept-Encoding"):
            self.send_header("X-Origin-" + name, self.headers.get(name, ""))
        self.end_headers()
        if self.command != "HEAD":
            if self.path == "/stream" and not compressed:
                self.wfile.write(body[:13])
                self.wfile.flush()
                time.sleep(1.5)
                self.wfile.write(body[13:])
            elif self.path == "/split":
                split = len(body) // 2 if compressed else body.index(b"</head>") + 3
                self.wfile.write(body[:split])
                self.wfile.flush()
                time.sleep(0.1)
                self.wfile.write(body[split:])
            else:
                self.wfile.write(body)
            self.wfile.flush()
    do_POST = do_GET
    do_HEAD = do_GET

server = ThreadingHTTPServer(("0.0.0.0", 443), Handler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("/fixture/cert.pem", "/fixture/key.pem")
ctx.set_servername_callback(lambda sock, name, context: setattr(sock, "sni", name or ""))
server.socket = ctx.wrap_socket(server.socket, server_side=True)
server.serve_forever()
'''


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


class ProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefix = "analytics-injector-test-" + uuid.uuid4().hex[:10]
        cls.tmp = tempfile.TemporaryDirectory(prefix=cls.prefix)
        cls.addClassCleanup(cls.tmp.cleanup)
        fixture = Path(cls.tmp.name)
        (fixture / "origin.py").write_text(ORIGIN)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(fixture / "key.pem"), "-out", str(fixture / "cert.pem"),
                        "-days", "1", "-subj", "/CN=origin"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        docker("network", "create", cls.prefix)
        cls.addClassCleanup(docker, "network", "rm", cls.prefix)
        origin = cls.prefix + "-origin"
        docker("run", "-d", "--name", origin, "--network", cls.prefix,
               "--network-alias", "cilium-gateway-gateway-external.gateway.svc.cluster.local",
               "-v", f"{fixture}:/fixture:ro", "python:3.13-alpine",
               "python", "/fixture/origin.py")
        cls.addClassCleanup(docker, "rm", "-f", origin)
        image = re.search(r"image:\s*(\S+)", (APP / "deployment.yaml").read_text()).group(1)
        cls.nginx = cls.prefix + "-nginx"
        docker("run", "-d", "--name", cls.nginx, "--network", cls.prefix,
               "--read-only", "--user", "101:101", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:uid=101,gid=101",
               "-p", "127.0.0.1::8080", "-p", "127.0.0.1::8081",
               "-v", f"{APP / 'default.conf'}:/etc/nginx/conf.d/default.conf:ro", image)
        cls.addClassCleanup(docker, "rm", "-f", cls.nginx)
        cls.port = int(docker("port", cls.nginx, "8080/tcp").rsplit(":", 1)[1])
        cls.health = int(docker("port", cls.nginx, "8081/tcp").rsplit(":", 1)[1])
        # A bare TCP connect isn't enough: docker-proxy accepts before nginx listens, then resets.
        deadline = time.monotonic() + 30
        while True:
            try:
                if cls.ready():
                    break
            except (OSError, http.client.HTTPException):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError(docker("logs", cls.nginx))
            time.sleep(0.2)
        docker("exec", cls.nginx, "nginx", "-t")

    @classmethod
    def ready(cls):
        for port, host in ((cls.health, "localhost"), (cls.port, "deals.vanillax.me")):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                path = "/healthz" if port == cls.health else "/"
                conn.request("GET", path, headers={"Host": host})
                if conn.getresponse().status >= 500:
                    return False
            finally:
                conn.close()
        return True

    def request(self, path="/", host="deals.vanillax.me", method="GET", headers=None, port=None):
        conn = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=5)
        self.addCleanup(conn.close)
        base = {"Host": host, "User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.8"}
        conn.request(method, path, headers={**base, **(headers or {})})
        return conn.getresponse()

    def test_html_injection_and_tls_forwarding(self):
        headers = {"Accept-Encoding": "gzip", "Authorization": "Bearer fixture",
                   "CF-Connecting-IP": "198.51.100.10", "X-Forwarded-For": "198.51.100.10"}
        r = self.request("/page?foo=bar", headers=headers)
        body = r.read()
        self.assertEqual(r.status, 200)
        self.assertEqual(body.count(MARKER), 1)
        self.assertIn(b'/script.js" data-website-id="auto"', body)
        self.assertIn(b'/recorder.js" data-website-id="auto"', body)
        self.assertIn(b"--></head>", body)
        self.assertEqual(r.getheader("Content-Security-Policy"), "default-src 'self'")
        self.assertEqual(r.getheader("X-Origin-Host"), "deals.vanillax.me")
        self.assertEqual(r.getheader("X-Origin-SNI"), "deals.vanillax.me")
        self.assertEqual(r.getheader("X-Origin-URI"), "/page?foo=bar")
        self.assertEqual(r.getheader("X-Origin-Accept-Encoding"), "gzip")
        self.assertIsNone(r.getheader("Content-Encoding"))
        for name in ("Authorization", "CF-Connecting-IP", "X-Forwarded-For"):
            self.assertEqual(r.getheader("X-Origin-" + name), headers[name])
        self.assertIsNone(r.getheader("Content-Length"))
        self.assertIsNone(r.getheader("ETag"))
        self.assertIsNone(r.getheader("Last-Modified"))

    def test_excluded_hosts_preserve_compression_and_validators(self):
        for name in ("libreddit", "ingest-umami", "umami", "otel",
                     "radar", "radar-ng-api", "radar-l2-shadow", "argocd-webhook"):
            with self.subTest(host=name):
                r = self.request(host=name + ".vanillax.me", headers={"Accept-Encoding": "gzip"})
                body = r.read()
                self.assertEqual(gzip.decompress(body), HTML)
                self.assertEqual(r.getheader("Content-Length"), str(len(body)))
                self.assertEqual(r.getheader("ETag"), '"origin"')
                self.assertIsNotNone(r.getheader("Last-Modified"))

    def test_assets_methods_status_and_content_type(self):
        for path, method, status in [("/asset.js", "GET", 200), ("/asset.CSS?x=1", "GET", 200),
                                      ("/", "POST", 200), ("/redirect", "GET", 302),
                                      ("/error", "GET", 500), ("/json", "GET", 200)]:
            with self.subTest(path=path, method=method):
                r = self.request(path, method=method)
                self.assertEqual(r.status, status)
                self.assertEqual(r.read(), HTML)
                # Pages are fetched gzipped and unzipped here, which weakens the validator.
                self.assertIn(r.getheader("ETag"), ('"origin"', 'W/"origin"'))
        for path, status in [("/empty", 204), ("/not-modified", 304)]:
            r = self.request(path)
            self.assertEqual(r.status, status)
            self.assertEqual(r.read(), b"")
        r = self.request(method="HEAD")
        self.assertEqual(r.read(), b"")
        self.assertEqual(r.getheader("Content-Length"), str(len(HTML)))

    def test_every_site_gets_the_same_tag_and_redlib_csp(self):
        for host in ("redlib.vanillax.me", "search.vanillax.me", "brand-new.vanillax.me"):
            with self.subTest(host=host):
                r = self.request(host=host)
                self.assertIn(b'data-website-id="auto"', r.read())
                csp = r.getheader("Content-Security-Policy")
                if host.startswith("redlib"):
                    self.assertIn("script-src 'self' blob: https://ingest-umami.vanillax.me", csp)
                    self.assertIn("connect-src 'self' https://ingest-umami.vanillax.me", csp)
                else:
                    self.assertEqual(csp, "default-src 'self'")

    def test_pages_are_fetched_gzipped_for_any_client(self):
        # Anubis challenges requests without gzip; the proxy unzips before tagging.
        for accept in ("", "br", "gzip, deflate, br, zstd"):
            with self.subTest(accept=accept):
                r = self.request(headers={"Accept-Encoding": accept, "User-Agent": "Mozilla/5.0"})
                body = r.read()
                self.assertEqual(r.getheader("X-Origin-Accept-Encoding"), "gzip")
                self.assertIsNone(r.getheader("Content-Encoding"))
                self.assertEqual(body.count(MARKER), 1)

    def test_request_without_user_agent_passes_through_intact(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.putrequest("GET", "/", skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", "deals.vanillax.me")
        conn.putheader("Accept-Encoding", "gzip")
        conn.putheader("Accept", "text/html")
        conn.endheaders()
        r = conn.getresponse()
        # gzip_disable matches user agents, so a UA-less client keeps the zipped, untagged page.
        self.assertEqual(gzip.decompress(r.read()), HTML)

    def test_non_page_requests_pass_through_untouched(self):
        for accept in ("*/*", "application/json", "text/event-stream"):
            with self.subTest(accept=accept):
                r = self.request(headers={"Accept": accept, "Accept-Encoding": "gzip"})
                body = r.read()
                self.assertEqual(gzip.decompress(body), HTML)
                self.assertEqual(r.getheader("ETag"), '"origin"')
                self.assertEqual(r.getheader("X-Origin-Accept-Encoding"), "gzip")

    def test_anubis_challenge_page_is_not_tagged(self):
        r = self.request("/anubis", host="redlib.vanillax.me")
        self.assertNotIn(MARKER, r.read())
        r = self.request("/anubis-cleared", host="redlib.vanillax.me")
        self.assertIn(MARKER, r.read())

    def test_apex_and_split_head(self):
        for path, host in [("/", "vanillax.me"), ("/upper", "deals.vanillax.me"),
                           ("/split", "deals.vanillax.me")]:
            with self.subTest(path=path, host=host):
                self.assertEqual(self.request(path, host=host).read().count(MARKER), 1)

    def test_health_does_not_shadow_application(self):
        self.assertIn(MARKER, self.request("/healthz").read())
        self.assertEqual(self.request("/healthz", port=self.health).read(), b"ok\n")

    def test_sse_is_streamed_without_waiting_for_completion(self):
        start = time.monotonic()
        r = self.request("/stream")
        self.assertEqual(r.read(13), b"data: first\n\n")
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(r.read(), b"data: second\n\n")

    def test_websocket_upgrade_and_bidirectional_data(self):
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            sock.sendall(b"GET /ws HTTP/1.1\r\nHost: deals.vanillax.me\r\n"
                         b"Connection: Upgrade\r\nUpgrade: websocket\r\n\r\n")
            data = b""
            while not data.endswith(b"\r\n\r\n"):
                chunk = sock.recv(1)
                self.assertTrue(chunk)
                data += chunk
            self.assertIn(b"101 Switching Protocols", data)
            sock.sendall(b"ping")
            self.assertEqual(sock.recv(4), b"ping")
