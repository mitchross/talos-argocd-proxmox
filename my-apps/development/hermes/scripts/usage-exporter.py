"""Prometheus exporter for Hermes model usage, read from Hermes's own state.db.

Each scrape sums the session_model_usage table (the same rows `hermes insights`
reads) by model, provider, task and session source. Values are running totals
over the history Hermes keeps, so read them with increase() in Grafana.

Prometheus's increase() treats a series' first sample as its starting point, so a
model's first call on a new surface or task was never counted (a single local Qwen
subagent call never showed). A label set that appears after startup is therefore
served as 0 for HOLD_SECONDS first, so Prometheus scrapes the zero and then counts
the real value. Label sets present at startup are history and are served as-is.
"""

import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB_PATH = os.environ.get("HERMES_STATE_DB", "/opt/data/state.db")
PORT = int(os.environ.get("PORT", "9464"))
CACHE_SECONDS = 30
# Two 60 s scrapes plus the cache, so at least one scrape sees the zero.
HOLD_SECONDS = 180
_first_seen = {}  # label set -> monotonic time first served; None = present at startup
_baseline = {"done": False}

QUERY = """
SELECT u.model,
       COALESCE(NULLIF(u.billing_provider, ''), 'unknown'),
       COALESCE(NULLIF(u.task, ''), 'main'),
       COALESCE(NULLIF(s.source, ''), 'unknown'),
       SUM(u.api_call_count),
       SUM(u.input_tokens), SUM(u.output_tokens),
       SUM(u.cache_read_tokens), SUM(u.cache_write_tokens), SUM(u.reasoning_tokens),
       SUM(CASE WHEN COALESCE(u.actual_cost_usd, 0) > 0
                THEN u.actual_cost_usd ELSE COALESCE(u.estimated_cost_usd, 0) END),
       COUNT(DISTINCT u.session_id)
FROM session_model_usage u
LEFT JOIN sessions s ON s.id = u.session_id
GROUP BY 1, 2, 3, 4
"""

TOKEN_TYPES = ("input", "output", "cache_read", "cache_write", "reasoning")

_lock = threading.Lock()
_cache = {"at": 0.0, "body": b""}


def _label(value):
    return str(value or "unknown").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render():
    lines = [
        "# HELP hermes_model_api_calls_total Model API calls made by Hermes.",
        "# TYPE hermes_model_api_calls_total counter",
        "# HELP hermes_model_tokens_total Tokens used by Hermes, by token type.",
        "# TYPE hermes_model_tokens_total counter",
        "# HELP hermes_model_cost_usd_total Cost in USD: actual when the provider reports it, else Hermes's estimate.",
        "# TYPE hermes_model_cost_usd_total counter",
        "# HELP hermes_model_sessions Sessions that used this model.",
        "# TYPE hermes_model_sessions gauge",
    ]
    started = time.monotonic()
    up = 1
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        try:
            rows = conn.execute(QUERY).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        rows, up = [], 0
    now = time.monotonic()
    for model, provider, task, source, calls, *rest in rows:
        tokens, cost, sessions = rest[:5], rest[5], rest[6]
        labels = (f'model="{_label(model)}",provider="{_label(provider)}",'
                  f'task="{_label(task)}",source="{_label(source)}"')
        # Label sets in the first successful read are history; later new ones start at 0.
        first = _first_seen.setdefault(labels, now if _baseline["done"] else None)
        if first is not None and now - first < HOLD_SECONDS:
            calls, tokens, cost = 0, [0] * len(tokens), 0
        lines.append(f"hermes_model_api_calls_total{{{labels}}} {int(calls or 0)}")
        for kind, value in zip(TOKEN_TYPES, tokens):
            lines.append(f'hermes_model_tokens_total{{{labels},type="{kind}"}} {int(value or 0)}')
        lines.append(f"hermes_model_cost_usd_total{{{labels}}} {float(cost or 0):.6f}")
        lines.append(f"hermes_model_sessions{{{labels}}} {int(sessions or 0)}")
    if up:
        _baseline["done"] = True
    lines += [
        "# HELP hermes_usage_exporter_up 1 when state.db was read on this scrape.",
        "# TYPE hermes_usage_exporter_up gauge",
        f"hermes_usage_exporter_up {up}",
        "# HELP hermes_usage_exporter_query_seconds Time spent reading state.db.",
        "# TYPE hermes_usage_exporter_query_seconds gauge",
        f"hermes_usage_exporter_query_seconds {time.monotonic() - started:.4f}",
    ]
    return ("\n".join(lines) + "\n").encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/metrics", "/"):
            self.send_error(404)
            return
        with _lock:
            if time.monotonic() - _cache["at"] > CACHE_SECONDS:
                _cache["body"], _cache["at"] = render(), time.monotonic()
            body = _cache["body"]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
