"""Inference dashboards: engine isolation, health semantics, units and unsupported metrics."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / "monitoring/metrics/prometheus-stack/dashboards/ai"
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts/generate-inference-dashboards.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

# What Strata d5ea713 serve/prometheus.py renders (vLLM names and native strata: facts).
STRATA_VLLM = {
    "vllm:num_requests_running", "vllm:num_requests_waiting", "vllm:kv_cache_usage_perc",
    "vllm:prompt_tokens_total", "vllm:generation_tokens_total", "vllm:request_success_total",
    "vllm:prefix_cache_queries_total", "vllm:prefix_cache_hits_total", "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total", "vllm:num_preemptions_total",
    "vllm:time_to_first_token_seconds", "vllm:inter_token_latency_seconds", "vllm:e2e_request_latency_seconds"}
STRATA_NATIVE = {
    "strata:live_state", "strata:live_tok_s", "strata:live_prefill_tok_s_mean", "strata:live_prompt_read",
    "strata:live_slots", "strata:engine_max_context", "strata:totals_prompt_seconds_total",
    "strata:totals_decode_seconds_total", "strata:last_hit_rate", "strata:last_decode_tok_s", "strata:gpu_util",
    "strata:gpu_mem_used_bytes", "strata:gpu_mem_total_bytes", "strata:gpu_temp_celsius", "strata:gpu_power_watts",
    "strata:cpu", "strata:ram_used_bytes", "strata:ram_total_bytes"}
ENGINE_UIDS = {"vllm-inference": "vllm", "strata-inference": "strata"}
METRIC = re.compile(r"\b((?:vllm|strata):[a-z0-9_]+)")
SELECTOR = re.compile(r"([A-Za-z_:][A-Za-z0-9_:]*)\{([^}]*)\}")
AGG = re.compile(r"\b(sum|max|min|avg|count)\s*(?:by\s*\(([^)]*)\))?\s*\(")


def base(name):
    return re.sub(r"_(bucket|sum|count)$", "", name)


def boards():
    return {name: json.loads((AI / name).read_text()) for name in gen.BOARDS}


def targets(board):
    for panel in board["panels"]:
        for t in panel.get("targets", []):
            yield panel, t


class GeneratedFiles(unittest.TestCase):
    def test_committed_json_matches_generator(self):
        for name, board in gen.build().items():
            self.assertEqual((AI / name).read_text(), gen.render(board),
                             f"{name} is stale: run scripts/generate-inference-dashboards.py")

    def test_dashboard_conventions(self):
        for name, board in boards().items():
            self.assertIsNone(board["id"])
            self.assertFalse(board["editable"])
            self.assertEqual(name, board["uid"] + ".json")
            text = json.dumps(board)
            self.assertNotIn("${DS", text)
            self.assertNotIn("__inputs", text)
            for panel, t in targets(board):
                self.assertEqual(panel["datasource"], gen.DS, panel["title"])
                self.assertEqual(t["datasource"], gen.DS, panel["title"])
                self.assertNotIn("_expect", t)

    def test_kustomization_lists_every_dashboard(self):
        kustomization = (AI / "kustomization.yaml").read_text()
        for path in AI.glob("*.json"):
            self.assertEqual(kustomization.count(f"- {path.name}\n"), 1, path.name)
        self.assertEqual(kustomization.count("files:"), len(list(AI.glob("*.json"))))


class EngineIsolation(unittest.TestCase):
    def test_engine_boards_pin_their_namespace(self):
        for uid, ns in ENGINE_UIDS.items():
            for panel, t in targets(boards()[uid + ".json"]):
                expr = t["expr"]
                self.assertNotIn("namespace=~", expr, panel["title"])
                for name in METRIC.findall(expr):
                    self.assertRegex(expr, re.escape(name) + r"(_bucket|_sum|_count)?\{", panel["title"])
                for name, labels in SELECTOR.findall(expr):
                    if name.startswith("DCGM_"):
                        self.assertIn(f'exported_namespace="{ns}"', labels, panel["title"])
                    else:
                        self.assertIn(f'namespace="{ns}"', labels, f"{uid} / {panel['title']}: {name}")

    def test_no_aggregation_mixes_engines(self):
        """Engine boards keep model_name; the overview keeps namespace whenever it spans both engines."""
        for name, board in boards().items():
            for panel, t in targets(board):
                expr = t["expr"]
                self.assertNotRegex(expr, r"\)\s*(by|without)\s*\(", "use prefix `sum by (...)` only")
                self.assertNotIn("without", expr)
                spans_both = 'namespace=~"vllm|strata"' in expr
                for op, by in AGG.findall(expr):
                    labels = {x.strip() for x in by.split(",")} if by else set()
                    where = f"{name} / {panel['title']} {t['refId']}: {op} by ({by})"
                    if spans_both:
                        self.assertTrue(labels & {"namespace", "exported_namespace"}, where)
                    elif not labels:
                        # label-less only for single-namespace state codes
                        self.assertNotIn("=~\"vllm|strata\"", expr, where)
                        self.assertTrue(re.search(r'namespace="(vllm|strata)"', expr), where)
                if "litellm_" not in expr and spans_both:
                    self.assertTrue(re.search(r"by \([^)]*namespace", expr), name + panel["title"])

    def test_strata_board_uses_only_metrics_strata_exports(self):
        for panel, t in targets(boards()["strata-inference.json"]):
            for name in METRIC.findall(t["expr"]):
                self.assertIn(base(name), STRATA_VLLM | STRATA_NATIVE, f"{panel['title']}: {name}")

    def test_overview_pins_engine_only_metrics(self):
        """A metric only one engine exports must be pinned to that engine in the overview."""
        for panel, t in targets(boards()["llm-engines.json"]):
            for name, labels in SELECTOR.findall(t["expr"]):
                if name.startswith("strata:"):
                    self.assertIn('namespace="strata"', labels, panel["title"])
                elif name.startswith("vllm:") and base(name) not in STRATA_VLLM:
                    self.assertIn('namespace="vllm"', labels, f"{panel['title']}: {name}")

    def test_model_variable_is_engine_scoped(self):
        for uid, ns in ENGINE_UIDS.items():
            (var,) = boards()[uid + ".json"]["templating"]["list"]
            self.assertIn(f'namespace="{ns}"', var["query"]["query"])
            self.assertEqual(var["allValue"], ".+")


class HealthSemantics(unittest.TestCase):
    def status_panels(self):
        for name, board in boards().items():
            for panel in board["panels"]:
                if panel.get("targets") and panel["targets"][0]["expr"].startswith(
                        "max(absent(kube_deployment_spec_replicas"):
                    yield name, panel

    def test_status_tiles_on_every_board(self):
        found = sorted((n, p["title"]) for n, p in self.status_panels())
        self.assertEqual(found, [("llm-engines.json", "Strata engine"), ("llm-engines.json", "vLLM engine"),
                                 ("strata-inference.json", "Strata engine"),
                                 ("vllm-inference.json", "vLLM engine")])

    def test_parked_is_neutral_and_checked_before_down(self):
        for name, panel in self.status_panels():
            codes = panel["fieldConfig"]["defaults"]["mappings"][0]["options"]
            self.assertTrue(codes["0"]["text"].startswith("Parked"))
            self.assertNotIn(codes["0"]["color"], ("red", "dark-red", "orange"))
            self.assertEqual(codes["1"]["color"], "red")
            self.assertEqual(codes["2"]["text"], "Serving")
            self.assertNotEqual(panel["fieldConfig"]["defaults"]["noValue"], "Down")
            expr = panel["targets"][0]["expr"]
            self.assertLess(expr.index("== 0) * 0 + 0"), expr.index(f"vector({gen.STATUS_DOWN})"))
            self.assertTrue(expr.startswith("max(absent(kube_deployment_spec_replicas"))

    def test_no_panel_reports_missing_data_as_down(self):
        for name, board in boards().items():
            for panel in board["panels"]:
                no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue")
                self.assertNotIn(no_value, ("Down", "0"), f"{name} / {panel['title']}")

    def test_promtool_fixture_covers_every_state(self):
        fixture = gen.promtool_fixture()
        for ns in gen.ENGINES:
            codes = {t["promql_expr_test"][0]["exp_samples"][0]["value"]
                     for t in fixture["tests"] if t["name"].startswith(ns + ":")}
            self.assertEqual(codes, {gen.STATUS_ABSENT, gen.STATUS_PARKED, gen.STATUS_DOWN, gen.STATUS_SERVING,
                                     gen.STATUS_WAIT})

    @unittest.skipUnless(os.environ.get("PROMTOOL"), "set PROMTOOL=/path/to/promtool to evaluate the PromQL")
    def test_status_expressions_evaluate_with_promtool(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen_out = subprocess.run(["python3", str(ROOT / "scripts/generate-inference-dashboards.py"),
                                      "--promtool-tests", tmp], capture_output=True, text=True)
            self.assertEqual(gen_out.returncode, 0, gen_out.stderr)
            run = subprocess.run([os.environ["PROMTOOL"], "test", "rules", "inference-status.test.yaml"],
                                 cwd=tmp, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


class UnitsAndMeaning(unittest.TestCase):
    @staticmethod
    def expected_unit(expr):
        if "histogram_quantile" in expr:
            return "s" if "_seconds_bucket" in expr else "short"
        if "DCGM_FI_DEV_TOTAL_ENERGY" in expr or re.search(r"/.*request_success_total", expr):
            return "short"                                  # Wh per 1k tokens, tokens per request
        if re.search(r"POWER_USAGE|gpu_power_watts", expr):
            return "watt"
        if re.search(r"GPU_TEMP|temp_celsius", expr):
            return "celsius"
        if re.search(r"GPU_UTIL|strata:gpu_util", expr):
            return "percent"
        if re.search(r"hits_total[^-]*/[^/]*queries_total|accepted_tokens_total|kv_cache_usage_perc|last_hit_rate"
                     r"|strata:cpu|ram_used", expr):
            return "percentunit"
        if re.search(r"_bytes|FB_USED", expr):
            return "bytes"
        if re.search(r"tok_s|tokens_(total|sum)|inter_token_latency_seconds_count", expr) and (
                "/" in expr or "rate(" in expr or "tok_s" in expr):
            return "tok/s"
        return None

    def test_units_match_the_quantity(self):
        for name, board in boards().items():
            for panel, t in targets(board):
                want = self.expected_unit(t["expr"])
                if panel["type"] == "state-timeline":       # mapped state codes, no unit
                    continue
                if panel["type"] == "table":
                    header = next(o for o in panel["transformations"][1]["options"]["renameByName"].items()
                                  if o[0] == f"Value #{t['refId']}")[1]
                    unit = next(p["value"] for o in panel["fieldConfig"]["overrides"]
                                if o["matcher"]["options"] == header for p in o["properties"] if p["id"] == "unit")
                else:
                    unit = panel["fieldConfig"]["defaults"]["unit"]
                if want:
                    self.assertEqual(unit, want, f"{name} / {panel['title']} {t['refId']}: {t['expr'][:90]}")
                if unit == "percentunit":
                    self.assertNotIn("* 100", t["expr"], panel["title"])

    def test_no_fake_zeros_or_static_benchmarks(self):
        for name, board in boards().items():
            text = json.dumps(board)
            self.assertNotIn("vector(0)", text)
            self.assertNotRegex(text, r"or on\s*\(\)\s*\d")
            for panel in board["panels"]:
                if panel["type"] == "text":
                    self.assertNotRegex(panel["options"]["content"], r"\d+\s*tok/s", "no static benchmark numbers")

    def test_unsupported_metrics_say_so(self):
        b = boards()
        strata = {p["title"]: p for p in b["strata-inference.json"]["panels"]}
        self.assertNotIn("queue_time", json.dumps(b["strata-inference.json"]))
        self.assertIn("Not exported", strata["Batch slots by state"]["fieldConfig"]["defaults"]["noValue"])
        vllm = {p["title"]: p for p in b["vllm-inference.json"]["panels"]}
        self.assertIn("MTP is off", vllm["Speculative decoding (MTP) acceptance"]["fieldConfig"]["defaults"]["noValue"])

    def test_titles_do_not_claim_single_request_speed(self):
        for name, board in boards().items():
            for panel, t in targets(board):
                self.assertNotIn("single-request", panel["title"].lower())
                if re.search(r"inter_token_latency_seconds_count.*/.*inter_token_latency_seconds_sum", t["expr"]):
                    header = panel.get("transformations", [{}, {"options": {}}])[1]["options"].get(
                        "renameByName", {}).get(f"Value #{t['refId']}", "")
                    label = (panel["title"] + " " + t["legendFormat"] + " " + header).lower()
                    self.assertTrue("per-stream" in label or "1 ÷ mean" in label, panel["title"])

    def test_strata_cache_panels_name_three_different_caches(self):
        strata = {p["title"]: p for p in boards()["strata-inference.json"]["panels"]}
        self.assertIn("not GPU KV memory", strata["Context used by the running request"]["description"])
        self.assertIn("last request", strata["Expert cache hit, last request"]["title"])
        self.assertIn("whole GPU node", strata["Node CPU and RAM (whole host)"]["description"])

    def test_overview_states_comparison_and_gateway_caveats(self):
        intro = boards()["llm-engines.json"]["panels"][0]["options"]["content"]
        self.assertIn("not a benchmark", intro)
        self.assertIn("never reaches these engines", intro)


class Navigation(unittest.TestCase):
    def test_inference_boards_link_each_other_and_context(self):
        for name, board in boards().items():
            urls = {l["url"] for l in board["links"]}
            want = {u for _, u in gen.LINKS} - {f"/d/{board['uid']}"}
            self.assertEqual(urls, want, name)

    def test_every_dashboard_link_resolves(self):
        dashboards = list((ROOT / "monitoring/metrics/prometheus-stack/dashboards").rglob("*.json"))
        uids = {json.loads(p.read_text())["uid"] for p in dashboards}
        self.assertIn("vllm-inference", uids)
        for path in dashboards:
            for uid in re.findall(r'"/d/([a-z0-9-]+)', path.read_text()):
                self.assertIn(uid, uids, f"{path.name} links /d/{uid}")

    def test_neighbouring_ai_boards_reach_the_overview(self):
        for name in ("gpu-overview.json", "ai-gateway-analytics.json", "hermes-ai-split.json"):
            links = {l["url"] for l in json.loads((AI / name).read_text())["links"]}
            self.assertIn("/d/llm-engines", links, name)


if __name__ == "__main__":
    unittest.main()
