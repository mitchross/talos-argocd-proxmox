#!/usr/bin/env python3
"""Generate the local LLM inference dashboards (vLLM, Strata, engine overview).

vLLM and Strata export the same `vllm:*` metric names, so every selector here pins
`namespace` and every aggregation keeps `namespace`/`model_name`. Edit this script, then run it;
never hand-edit the generated JSON. `--check` fails when the committed JSON is stale and
`--promtool-tests DIR` writes promtool fixtures for the engine-status expressions.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "monitoring/metrics/prometheus-stack/dashboards/ai"
DS = {"type": "prometheus", "uid": "prometheus"}

# Engine facts the queries depend on. Models are matched only by the validator's isolation check.
ENGINES = {
    "vllm": {"name": "vLLM", "deployment": "vllm-server", "job": "vllm-service",
             "container": "vllm-server", "uid": "vllm-inference", "model_regex": r"^qwen3\.8-27b"},
    "strata": {"name": "Strata", "deployment": "strata-server", "job": "strata-service",
               "container": "strata", "uid": "strata-inference", "model_regex": r"^qwen3\.8-flash-next"},
}
OVERVIEW_UID = "llm-engines"
BOTH = 'namespace=~"vllm|strata"'
BY = "namespace, model_name"

# Engine status codes shared by the status expression, its value mappings and the promtool fixtures.
STATUS_PARKED, STATUS_DOWN, STATUS_SERVING, STATUS_WAIT, STATUS_ABSENT = 0, 1, 2, 3, 4
STRATA_ACTIVITY = {"idle": 1, "reading": 2, "generating": 3, "unloaded": 4}

LINKS = [
    ("Local LLM Engines", f"/d/{OVERVIEW_UID}"),
    ("vLLM Inference", "/d/vllm-inference"),
    ("Strata Inference", "/d/strata-inference"),
    ("GPU Overview", "/d/gpu-overview"),
    ("AI Gateway and Analytics", "/d/ai-gateway-analytics"),
]


# --------------------------------------------------------------------------- building blocks

def target(expr, legend="__auto", ref="A", instant=False, table=False, expect="traffic"):
    t = {"datasource": DS, "refId": ref, "expr": expr, "legendFormat": legend,
         "instant": instant, "range": not instant}
    if table:
        t["format"] = "table"
    t["_expect"] = expect
    return t


def refs(*targets):
    """Assign refIds A, B, C... in order."""
    for i, t in enumerate(targets):
        t["refId"] = chr(ord("A") + i)
    return list(targets)


def thresholds(*steps):
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in steps]}


def mapping(codes):
    return [{"type": "value", "options": {str(k): {"text": text, "color": color}
                                          for k, (text, color) in codes.items()}}]


def stat(title, targets, unit="short", desc=None, decimals=None, no_value=None, mappings=None,
         steps=(("text", None),), color_mode="value", text_mode="auto", min_=None, max_=None):
    defaults = {"unit": unit, "thresholds": thresholds(*steps), "color": {"mode": "thresholds"},
                "mappings": mappings or []}
    if decimals is not None:
        defaults["decimals"] = decimals
    if no_value is not None:
        defaults["noValue"] = no_value
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    p = {"type": "stat", "title": title, "datasource": DS, "targets": refs(*targets),
         "fieldConfig": {"defaults": defaults, "overrides": []},
         "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                     "colorMode": color_mode, "graphMode": "none", "textMode": text_mode,
                     "justifyMode": "auto", "orientation": "auto", "wideLayout": True,
                     "showPercentChange": False}}
    for t in p["targets"]:
        t["instant"], t["range"] = True, False
    if desc:
        p["description"] = desc
    return p


def timeseries(title, targets, unit, desc=None, decimals=None, no_value=None, max_=None,
               interval=None, overrides=None, steps=(("green", None),), threshold_style="off",
               bars=False, step_line=False):
    custom = {"drawStyle": "bars" if bars else "line", "lineWidth": 2,
              "fillOpacity": 60 if bars else 10, "showPoints": "never", "pointSize": 4,
              "spanNulls": False, "lineInterpolation": "stepAfter" if step_line else "linear",
              "axisSoftMin": 0, "stacking": {"mode": "none", "group": "A"},
              "thresholdsStyle": {"mode": threshold_style}}
    defaults = {"unit": unit, "custom": custom, "color": {"mode": "palette-classic"},
                "thresholds": thresholds(*steps), "min": 0}
    for key, value in (("decimals", decimals), ("noValue", no_value), ("max", max_)):
        if value is not None:
            defaults[key] = value
    p = {"type": "timeseries", "title": title, "datasource": DS, "targets": refs(*targets),
         "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
         "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                     "tooltip": {"mode": "multi", "sort": "desc"}}}
    if interval:
        p["interval"] = interval
    if desc:
        p["description"] = desc
    return p


def state_timeline(title, targets, codes, desc=None, interval=None):
    p = {"type": "state-timeline", "title": title, "datasource": DS, "targets": refs(*targets),
         "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "mappings": mapping(codes),
                                      "thresholds": thresholds(("text", None)),
                                      "custom": {"fillOpacity": 80, "lineWidth": 0}},
                         "overrides": []},
         "options": {"showValue": "never", "rowHeight": 0.8, "mergeValues": True, "alignValue": "left",
                     "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                     "tooltip": {"mode": "single", "sort": "none"}}}
    if interval:
        p["interval"] = interval
    if desc:
        p["description"] = desc
    return p


def table(title, targets, columns, desc=None, no_value=None):
    """`columns` maps refId -> (header, unit, decimals); one row per (namespace, model_name)."""
    rename = {"namespace": "Engine (namespace)", "model_name": "Model"}
    order = {"namespace": 0, "model_name": 1}
    overrides = []
    for i, (ref, (header, unit, decimals)) in enumerate(columns.items()):
        rename[f"Value #{ref}"] = header
        order[f"Value #{ref}"] = i + 2
        props = [{"id": "unit", "value": unit}]
        if decimals is not None:
            props.append({"id": "decimals", "value": decimals})
        overrides.append({"matcher": {"id": "byName", "options": header}, "properties": props})
    defaults = {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}, "mappings": [],
                "thresholds": thresholds(("text", None)), "color": {"mode": "thresholds"}}
    if no_value is not None:
        defaults["noValue"] = no_value
    p = {"type": "table", "title": title, "datasource": DS, "targets": refs(*targets),
         "fieldConfig": {"defaults": defaults, "overrides": overrides},
         "options": {"showHeader": True, "cellHeight": "sm",
                     "footer": {"show": False, "reducer": ["sum"], "countRows": False, "fields": ""}},
         "transformations": [
             {"id": "merge", "options": {}},
             {"id": "organize", "options": {"excludeByName": {"Time": True}, "indexByName": order,
                                            "renameByName": rename}}]}
    for t in p["targets"]:
        t["instant"], t["range"], t["format"] = True, False, "table"
    if desc:
        p["description"] = desc
    return p


def text(content, title=""):
    return {"type": "text", "title": title,
            "options": {"mode": "markdown", "content": content,
                        "code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False}}}


def row(title):
    return {"type": "row", "title": title, "collapsed": False, "panels": []}


def layout(items):
    """items: rows (full width) or (panel, w, h). Panels flow left to right and wrap at 24."""
    panels, x, y, line_h = [], 0, 0, 0
    for item in items:
        if isinstance(item, dict):                    # a row
            if x:
                y, x, line_h = y + line_h, 0, 0
            item["gridPos"] = {"x": 0, "y": y, "w": 24, "h": 1}
            panels.append(item)
            y += 1
            continue
        panel, w, h = item
        if x + w > 24:
            y, x, line_h = y + line_h, 0, 0
        panel["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
        panels.append(panel)
        x += w
        line_h = max(line_h, h)
    for i, p in enumerate(panels, start=1):
        p["id"] = i
    return panels


def dashboard(uid, title, desc, tags, panels, time_from, variables=(), refresh="30s"):
    return {
        "id": None, "uid": uid, "title": title, "description": desc, "tags": tags,
        "timezone": "browser", "editable": False, "graphTooltip": 1, "fiscalYearStartMonth": 0,
        "liveNow": False, "schemaVersion": 42, "time": {"from": time_from, "to": "now"},
        "refresh": refresh, "annotations": {"list": []}, "templating": {"list": list(variables)},
        "links": [{"title": t, "type": "link", "url": u, "icon": "dashboard", "targetBlank": False,
                   "keepTime": True, "includeVars": False, "asDropdown": False, "tags": []}
                  for t, u in LINKS if u != f"/d/{uid}"],
        "panels": panels,
    }


def model_variable(ns):
    query = f'label_values(vllm:generation_tokens_total{{namespace="{ns}"}}, model_name)'
    return {"name": "model", "label": "Model", "type": "query", "datasource": DS,
            "query": {"query": query, "refId": "PrometheusVariableQueryEditor-VariableQuery"},
            "definition": query, "refresh": 2, "includeAll": True, "multi": True, "allValue": ".+",
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "options": [], "sort": 1, "hide": 0}


# --------------------------------------------------------------------------- shared queries

def sel(ns, extra=""):
    """Engine-board selector: pinned namespace plus the model picker."""
    body = f'namespace="{ns}", model_name=~"$model"'
    return "{" + body + (", " + extra if extra else "") + "}"


def osel(extra=""):
    """Overview selector: both engines, always aggregated by namespace."""
    return "{" + BOTH + (", " + extra if extra else "") + "}"


def status_expr(ns, waiting_rule=None):
    """One code per engine: Not deployed, Parked (0 replicas), Not serving, waiting state, Serving."""
    e = ENGINES[ns]
    replicas = f'kube_deployment_spec_replicas{{namespace="{ns}", deployment="{e["deployment"]}"}}'
    up = f'up{{namespace="{ns}", job="{e["job"]}"}}'
    parts = [f"max(absent({replicas})) * {STATUS_ABSENT}",
             f"(max({replicas}) == 0) * 0 + {STATUS_PARKED}",
             f"(max({up}) == 0) * 0 + {STATUS_DOWN}"]
    if waiting_rule:
        parts.append(f"({waiting_rule}) * 0 + {STATUS_WAIT}")
    parts += [f"(max({up}) == 1) * 0 + {STATUS_SERVING}", f"vector({STATUS_DOWN})"]
    return "\n  or ".join(parts)


STATUS_WAIT_RULES = {
    "vllm": 'max(vllm:engine_sleep_state{namespace="vllm", sleep_state="awake"}) == 0',
    "strata": 'max(strata:live_state{namespace="strata", state="unloaded"}) == 1',
}


def status_codes(ns):
    wait = {"vllm": "Asleep", "strata": "Loading model"}[ns]
    return {STATUS_PARKED: ("Parked (0 replicas)", "blue"), STATUS_DOWN: ("Not serving", "red"),
            STATUS_SERVING: ("Serving", "green"), STATUS_WAIT: (wait, "orange"),
            STATUS_ABSENT: ("Not deployed", "text")}


def status_stat(ns, title=None):
    name = ENGINES[ns]["name"]
    return stat(title or f"{name} engine", [target(status_expr(ns, STATUS_WAIT_RULES[ns]), expect="status")],
                mappings=mapping(status_codes(ns)), color_mode="background", no_value="Unknown",
                desc=f"From Git replicas, the {name} scrape target and its own state. Parked means 0 replicas "
                     "on purpose (the other engine has the cards), not an outage.")


def hist(metric, q, sel_, by):
    return f"histogram_quantile({q}, sum by (le, {by}) (rate({metric}_bucket{sel_}[$__rate_interval])))"


def hist_range(metric, q, sel_, by):
    return f"histogram_quantile({q}, sum by (le, {by}) (increase({metric}_bucket{sel_}[$__range])))"


def ratio(num, den, by, window="$__rate_interval", fn="rate"):
    return f"sum by ({by}) ({fn}({num}[{window}])) / sum by ({by}) ({fn}({den}[{window}]))"


def latency_panels(s, by, legend_prefix, metrics, interval=None, descs=None):
    out = []
    for title, metric, quantiles in metrics:
        ts = [target(hist(metric, q, s, by), f"{legend_prefix}p{int(float(q) * 100)}") for q in quantiles]
        out.append(timeseries(title, ts, "s", desc=(descs or {}).get(metric), decimals=2,
                              no_value="No finished requests in this range", interval=interval))
    return out


def hardware_dcgm(ns):
    d = f'{{exported_namespace="{ns}"}}'
    return [
        timeseries("GPU utilization (DCGM)", [target(f"max by (gpu) (DCGM_FI_DEV_GPU_UTIL{d})", "GPU {{gpu}}",
                                                     expect="live")], "percent", max_=100,
                   no_value="No GPU held by this engine"),
        timeseries("GPU power (DCGM)", [target(f"max by (gpu) (DCGM_FI_DEV_POWER_USAGE{d})", "GPU {{gpu}}",
                                               expect="live")], "watt",
                   desc="Red line = the 220 W per-card cap set on the host.",
                   steps=(("green", None), ("red", 220)), threshold_style="line",
                   no_value="No GPU held by this engine"),
        timeseries("GPU memory used (DCGM)", [target(f"max by (gpu) (DCGM_FI_DEV_FB_USED{d}) * 1024 * 1024",
                                                     "GPU {{gpu}}", expect="live")], "bytes",
                   no_value="No GPU held by this engine"),
        timeseries("GPU core temperature (DCGM)", [target(f"max by (gpu) (DCGM_FI_DEV_GPU_TEMP{d})", "GPU {{gpu}}",
                                                          expect="live")], "celsius",
                   no_value="No GPU held by this engine"),
    ]


def pod_resources(ns):
    c = ENGINES[ns]["container"]
    pod = f'namespace="{ns}", container="{c}"'
    return [
        timeseries("Pod CPU (cores)", [target(f"sum by (pod) (rate(container_cpu_usage_seconds_total{{{pod}}}"
                                              "[$__rate_interval]))", "{{pod}}", expect="live")],
                   "short", decimals=1, no_value="No pod running"),
        timeseries("Pod memory vs limit", refs(
            target(f"sum by (pod) (container_memory_working_set_bytes{{{pod}}})", "working set {{pod}}",
                   expect="live"),
            target(f'max by (pod) (kube_pod_container_resource_limits{{{pod}, resource="memory"}})',
                   "limit {{pod}}", expect="live")), "bytes", no_value="No pod running"),
    ]


# --------------------------------------------------------------------------- vLLM board

def vllm_board():
    ns, by, lp = "vllm", "model_name", ""
    s = lambda extra="": sel(ns, extra)                                          # noqa: E731
    gen = f"vllm:generation_tokens_total{s()}"
    computed, cached = s('source="local_compute"'), s('source="local_cache_hit"')
    intro = text(
        "**vLLM only.** Every query here is pinned to `namespace=\"vllm\"`. Strata exports the same `vllm:` "
        "metric names from its own namespace and has its own board, so nothing here mixes engines. "
        "When the engine tile says **Parked**, vLLM is at 0 replicas on purpose and empty panels are expected: "
        "widen the time range to see earlier runs. Model, flags and staging: `my-apps/ai/vllm/README.md`. "
        "Engines side by side: **Local LLM Engines**.")
    panels = [
        (intro, 24, 3),
        row("Now"),
        (status_stat(ns), 4, 4),
        (stat("Requests running", [target(f"sum by ({by}) (vllm:num_requests_running{s()})", expect="live")],
              no_value="Engine not running"), 3, 4),
        (stat("Requests waiting", [target(f"sum by ({by}) (vllm:num_requests_waiting{s()})", expect="live")],
              no_value="Engine not running", steps=(("green", None), ("orange", 1))), 3, 4),
        (stat("Generated tokens/s now", [target(f"sum by ({by}) (rate({gen}[$__rate_interval]))", expect="live")],
              unit="tok/s", decimals=1, no_value="Engine not running",
              desc="Wall clock across all running requests: idle time counts, so it reads 0 between requests."),
         4, 4),
        (stat("KV cache used", [target(f"max by ({by}) (vllm:kv_cache_usage_perc{s()})", expect="live")],
              unit="percentunit", decimals=1, no_value="Engine not running", min_=0, max_=1,
              steps=(("green", None), ("orange", 0.8), ("red", 0.95)),
              desc="Share of vLLM's GPU KV block pool in use (1 = full); a full pool queues or preempts."), 4, 4),
        (stat("Prefix cache hit (range)", [target(ratio(f"vllm:prefix_cache_hits_total{s()}",
                                                        f"vllm:prefix_cache_queries_total{s()}", by,
                                                        "$__range", "increase"))],
              unit="percentunit", decimals=1, no_value="No prompts in range",
              desc="Prompt tokens served from the GPU prefix cache instead of recomputed."), 3, 4),
        (stat("Requests finished (range)", [target(f"sum by ({by}) (increase(vllm:request_success_total{s()}"
                                                   "[$__range]))")],
              decimals=0, no_value="None in range"), 3, 4),
        row("Speed over the selected range"),
        (stat("Per-stream decode speed (range)", [target(
            ratio(f"vllm:request_generation_tokens_sum{s()}", f"vllm:request_decode_time_seconds_sum{s()}",
                  by, "$__range", "increase"))], unit="tok/s", decimals=1, no_value="No finished requests",
              desc="Generated tokens ÷ summed per-request decode time. Concurrent requests each count their own "
                   "time, so this is the speed one stream sees, not the batch total."), 6, 4),
        (stat("Per-stream speed, 1 ÷ mean inter-token latency (range)", [target(
            ratio(f"vllm:inter_token_latency_seconds_count{s()}", f"vllm:inter_token_latency_seconds_sum{s()}",
                  by, "$__range", "increase"))], unit="tok/s", decimals=1, no_value="No finished requests",
              desc="Token-weighted across every stream in the range; long answers dominate. Not one request."),
         6, 4),
        (stat("Prefill speed (range)", [target(
            f"sum by ({by}) (increase(vllm:prompt_tokens_by_source_total{computed}[$__range]))"
            f" / sum by ({by}) (increase(vllm:request_prefill_time_seconds_sum{s()}[$__range]))")],
              unit="tok/s", decimals=0, no_value="No finished requests",
              desc="Computed (not cached) prompt tokens ÷ summed per-request prefill time."), 6, 4),
        (stat("Wall-clock generation throughput (range)", [target(
            f"sum by ({by}) (increase({gen}[$__range])) / $__range_s")], unit="tok/s", decimals=2,
              no_value="No tokens in range",
              desc="All generated tokens ÷ the whole range, idle time included: a busy-ness number, not speed."),
         6, 4),
        row("Throughput"),
        (timeseries("Tokens per second (wall clock)", [
            target(f"sum by ({by}) (rate({gen}[$__rate_interval]))", f"{lp}generated"),
            target(f"sum by ({by}) (rate(vllm:prompt_tokens_by_source_total{computed}"
                   "[$__rate_interval]))", f"{lp}prompt: computed"),
            target(f"sum by ({by}) (rate(vllm:prompt_tokens_by_source_total{cached}"
                   "[$__rate_interval]))", f"{lp}prompt: from cache")], "tok/s", decimals=1,
            desc="Idle time counts as 0. Prompt tokens split into computed (prefill work) and prefix-cache hits.",
            no_value="No traffic in this range"), 8, 8),
        (timeseries("Per-stream decode speed", [
            target(ratio(f"vllm:request_generation_tokens_sum{s()}", f"vllm:request_decode_time_seconds_sum{s()}",
                         by), "tokens ÷ decode time"),
            target(ratio(f"vllm:inter_token_latency_seconds_count{s()}",
                         f"vllm:inter_token_latency_seconds_sum{s()}", by), "1 ÷ mean inter-token latency")],
            "tok/s", decimals=1, no_value="No finished requests in this range",
            desc="Speed one stream sees while generating, averaged over every stream in the window."), 8, 8),
        (timeseries("Prefill speed", [target(
            f"sum by ({by}) (rate(vllm:prompt_tokens_by_source_total{computed}"
            f"[$__rate_interval])) / sum by ({by}) (rate(vllm:request_prefill_time_seconds_sum{s()}"
            "[$__rate_interval]))", "computed prompt tokens ÷ prefill time")], "tok/s", decimals=0,
            no_value="No finished requests in this range"), 8, 8),
        row("Latency (finished requests)"),
        *[(p, 6, 8) for p in latency_panels(s(), by, lp, [
            ("Time to first token", "vllm:time_to_first_token_seconds", ("0.50", "0.95", "0.99")),
            ("End-to-end request time", "vllm:e2e_request_latency_seconds", ("0.50", "0.95", "0.99")),
            ("Inter-token latency", "vllm:inter_token_latency_seconds", ("0.50", "0.95", "0.99")),
            ("Queue wait", "vllm:request_queue_time_seconds", ("0.50", "0.95"))], descs={
            "vllm:time_to_first_token_seconds": "Includes queue wait and prefill.",
            "vllm:e2e_request_latency_seconds": "Reasoning is on by default, so long answers are normal.",
            "vllm:inter_token_latency_seconds": "Gap between two output tokens of one stream.",
            "vllm:request_queue_time_seconds": "Waiting for a batch slot or KV room before prefill starts."})],
        row("Capacity and outcomes"),
        (timeseries("KV cache usage", [target(f"max by ({by}) (vllm:kv_cache_usage_perc{s()})", "KV cache used",
                                              expect="live")], "percentunit", max_=1, decimals=1,
                    no_value="Engine not running"), 8, 8),
        (timeseries("Running vs waiting", [
            target(f"sum by ({by}) (vllm:num_requests_running{s()})", "running", expect="live"),
            target(f"sum by ({by}, reason) (vllm:num_requests_waiting_by_reason{s()})", "waiting: {{reason}}",
                   expect="live")], "short", decimals=0, no_value="Engine not running"), 8, 8),
        (timeseries("Finished requests by reason", [target(
            f"sum by ({by}, finished_reason) (increase(vllm:request_success_total{s()}[$__interval])) > 0",
            "{{finished_reason}}")], "short", decimals=0, bars=True, no_value="None in this range",
            desc="stop = normal finish, length = hit the max-token limit, abort = client went away."), 8, 8),
        (timeseries("Request size (finished requests)", [
            target(hist("vllm:request_prompt_tokens", "0.50", s(), by), "prompt p50"),
            target(hist("vllm:request_prompt_tokens", "0.95", s(), by), "prompt p95"),
            target(hist("vllm:request_generation_tokens", "0.50", s(), by), "generated p50"),
            target(hist("vllm:request_generation_tokens", "0.95", s(), by), "generated p95")], "short",
            decimals=0, no_value="No finished requests in this range",
            desc="Tokens per request; bigger prompts and answers change every speed and latency number."),
         12, 8),
        (timeseries("Speculative decoding (MTP) acceptance", [target(ratio(
            f"vllm:spec_decode_num_accepted_tokens_total{s()}", f"vllm:spec_decode_num_draft_tokens_total{s()}",
            by), "accepted ÷ drafted", expect="optional")], "percentunit", max_=1, decimals=1,
            no_value="No spec-decode series: MTP is off on vLLM",
            desc="Only exists when vLLM runs with speculative decoding."), 12, 8),
        row("Hardware (cards held by vLLM)"),
        *[(p, 6, 8) for p in hardware_dcgm(ns)],
        *[(p, 12, 7) for p in pod_resources(ns)],
    ]
    return dashboard(
        "vllm-inference", "vLLM Inference",
        "vLLM only (namespace vllm): engine state, throughput, decode and prefill speed, latency, queue, KV "
        "cache and its GPUs. Parked (0 replicas) is a normal state when another engine has the cards.",
        ["ai", "vllm", "llm"], layout(panels), "now-6h", [model_variable(ns)])


# --------------------------------------------------------------------------- Strata board

def strata_board():
    ns, by = "strata", "model_name"
    s = lambda extra="": sel(ns, extra)                                          # noqa: E731
    gen = f"vllm:generation_tokens_total{s()}"
    new_prompt = (f"(sum by ({by}) (increase(vllm:prefix_cache_queries_total{s()}[W])) - "
                  f"sum by ({by}) (increase(vllm:prefix_cache_hits_total{s()}[W])))")
    s_reading, s_generating = s('state="reading"'), s('state="generating"')
    reading = f"max by ({by}) (strata:live_state{s_reading}) == 1"
    generating = f"max by ({by}) (strata:live_state{s_generating}) == 1"
    activity = " or ".join(f'strata:live_state{{namespace="strata", state="{k}"}} * {v}'
                           for k, v in STRATA_ACTIVITY.items())
    activity_codes = {0: ("No state", "text"), 1: ("Idle", "green"), 2: ("Reading prompt", "blue"),
                      3: ("Generating", "purple"), 4: ("Unloaded", "orange")}
    iv = "2m"
    intro = text(
        "**Strata only.** Every query is pinned to `namespace=\"strata\"`. Strata exports vLLM's metric names "
        "plus its own `strata:` facts (upstream `docs/DETAILS.md`). It updates token counters, cache counters and "
        "latency histograms **when a request finishes**, so rates step at completions, and its TTFT clock starts "
        "after the request leaves the queue. It exports no queue-time histogram. Settings: "
        "`my-apps/ai/strata/README.md`. Engines side by side: **Local LLM Engines**.")
    panels = [
        (intro, 24, 3),
        row("Now"),
        (status_stat(ns), 4, 4),
        (stat("Activity", [target(f"max({activity})", expect="live")], mappings=mapping(activity_codes),
              color_mode="background", no_value="Engine not running",
              desc="strata:live_state for the newest request: idle, reading the prompt, or generating."), 4, 4),
        (stat("Requests running", [target(f"sum by ({by}) (vllm:num_requests_running{s()})", expect="live")],
              no_value="Engine not running"), 3, 4),
        (stat("Requests waiting", [target(f"sum by ({by}) (vllm:num_requests_waiting{s()})", expect="live")],
              no_value="Engine not running", steps=(("green", None), ("orange", 1)),
              desc="Queued for the engine or a batch slot. LiteLLM caps the gateway at the slot count."), 3, 4),
        (stat("Live decode speed", [target(f"max by ({by}) (strata:live_tok_s{s()}) and on ({by}) ({generating})",
                                           expect="optional")],
              unit="tok/s", decimals=1, no_value="Not generating",
              desc="strata:live_tok_s over the last seconds; shown only while a request is generating."), 4, 4),
        (stat("Live prefill speed", [target(
            f"max by ({by}) (strata:live_prefill_tok_s_mean{s()}) and on ({by}) ({reading})", expect="optional")],
              unit="tok/s", decimals=0, no_value="Not reading a prompt",
              desc="Mean prompt-reading rate of the running request, excluding its cached prefix."), 3, 4),
        (stat("Context window", [target(f"max by ({by}) (strata:engine_max_context{s()})", expect="live")],
              unit="short", decimals=0, no_value="Engine not running", desc="strata:engine_max_context, tokens."),
         3, 4),
        row("Speed over the selected range"),
        (stat("Active decode speed (range)", [target(
            ratio(gen, f"strata:totals_decode_seconds_total{s()}", by, "$__range", "increase"))],
              unit="tok/s", decimals=1, no_value="No finished requests",
              desc="Generated tokens ÷ Strata's decode time: speed while generating, idle time excluded."), 6, 4),
        (stat("Last request decode speed", [target(f"max by ({by}) (strata:last_decode_tok_s{s()})",
                                                   expect="optional")],
              unit="tok/s", decimals=1, no_value="No request since start",
              desc="strata:last_decode_tok_s: the most recent finished request only. It keeps its value while "
                   "idle, so it is not a live reading."), 6, 4),
        (stat("Active prefill speed (range)", [target(
            new_prompt.replace("[W]", "[$__range]") +
            f" / sum by ({by}) (increase(strata:totals_prompt_seconds_total{s()}[$__range]))")],
              unit="tok/s", decimals=0, no_value="No finished requests",
              desc="Newly read prompt tokens (prompt − reused) ÷ Strata's prompt-reading time."), 6, 4),
        (stat("Wall-clock generation throughput (range)", [target(
            f"sum by ({by}) (increase({gen}[$__range])) / $__range_s")], unit="tok/s", decimals=2,
              no_value="No tokens in range",
              desc="All generated tokens ÷ the whole range, idle time included: a busy-ness number, not speed."),
         6, 4),
        row("Throughput and decode"),
        (timeseries("Decode speed while generating", [
            target(ratio(gen, f"strata:totals_decode_seconds_total{s()}", by), "tokens ÷ decode time (window)"),
            target(f"max by ({by}) (strata:live_tok_s{s()}) and on ({by}) ({generating})", "live (generating only)",
                   expect="optional"),
            target(f"max by ({by}) (strata:last_decode_tok_s{s()})", "last finished request", expect="optional")],
            "tok/s", decimals=1, interval=iv, no_value="No finished requests in this range",
            desc="Window line = finished requests' tokens ÷ their decode time. Live = the running request. "
                 "Last request holds its value while idle."), 12, 8),
        (timeseries("Tokens per second (wall clock)", [
            target(f"sum by ({by}) (rate({gen}[$__rate_interval]))", "generated"),
            target(new_prompt.replace("increase(", "rate(").replace("[W]", "[$__rate_interval]"), "prompt: read"),
            target(f"sum by ({by}) (rate(vllm:prefix_cache_hits_total{s()}[$__rate_interval]))",
                   "prompt: reused from cache")], "tok/s", decimals=1, interval=iv,
            no_value="No finished requests in this range",
            desc="Idle time counts as 0, and counters move only when a request finishes."), 12, 8),
        (timeseries("Prefill speed while reading", [
            target(new_prompt.replace("increase(", "rate(").replace("[W]", "[$__rate_interval]") +
                   f" / sum by ({by}) (rate(strata:totals_prompt_seconds_total{s()}[$__rate_interval]))",
                   "read prompt tokens ÷ prompt time (window)"),
            target(f"max by ({by}) (strata:live_prefill_tok_s_mean{s()}) and on ({by}) ({reading})",
                   "live (reading only)", expect="optional")], "tok/s", decimals=0, interval=iv,
            no_value="No finished requests in this range"), 12, 8),
        (state_timeline("What the engine is doing", [target(f"max({activity})", "state", expect="live")],
                        activity_codes, interval="30s",
                        desc="Sampled every scrape (30 s); short reads between scrapes can be missed."), 12, 8),
        row("Latency (finished requests)"),
        *[(p, 8, 8) for p in latency_panels(s(), by, "", [
            ("Time to first token", "vllm:time_to_first_token_seconds", ("0.50", "0.95", "0.99")),
            ("End-to-end request time", "vllm:e2e_request_latency_seconds", ("0.50", "0.95", "0.99")),
            ("Inter-token gap (per-request means)", "vllm:inter_token_latency_seconds", ("0.50", "0.95"))],
            interval=iv, descs={
            "vllm:time_to_first_token_seconds": "Starts after the request leaves Strata's queue; prompt reading "
                                                "dominates.",
            "vllm:inter_token_latency_seconds": "Strata records each request's mean gap once per token, so these "
                                                "are percentiles of request averages, not single gaps."})],
        row("Concurrency"),
        (timeseries("Running vs waiting", [
            target(f"sum by ({by}) (vllm:num_requests_running{s()})", "running", expect="live"),
            target(f"sum by ({by}) (vllm:num_requests_waiting{s()})", "waiting", expect="live")],
            "short", decimals=0, step_line=True, no_value="Engine not running"), 12, 7),
        (timeseries("Batch slots by state", [target(f"sum by ({by}, state) (strata:live_slots{s()})", "{{state}}",
                                                    expect="optional")], "short", decimals=0, step_line=True,
                    no_value="Not exported: Strata lists slots only with batch slots on (PARALLEL > 1)"), 12, 7),
        row("Three different caches"),
        (stat("Prompt cache reuse (range)", [target(ratio(f"vllm:prefix_cache_hits_total{s()}",
                                                          f"vllm:prefix_cache_queries_total{s()}", by,
                                                          "$__range", "increase"))],
              unit="percentunit", decimals=1, no_value="No prompts in range",
              desc="Prompt tokens Strata already held from an earlier turn (vllm:prefix_cache_*)."), 6, 4),
        (stat("Expert cache hit, last request", [target(f"max by ({by}) (strata:last_hit_rate{s()})",
                                                        expect="optional")],
              unit="percentunit", decimals=1, no_value="No request since start",
              desc="VRAM share of the experts the last request looked up; experts read over PCIe are not counted."),
         6, 4),
        (stat("Context used by the running request", [target(f"max by ({by}) (vllm:kv_cache_usage_perc{s()})",
                                                              expect="live")],
              unit="percentunit", decimals=1, no_value="Engine not running", min_=0, max_=1,
              desc="Strata reports the running request's tokens ÷ its context window under this vLLM name; "
                   "it is not GPU KV memory and reads 0 when idle."), 6, 4),
        (stat("MTP draft acceptance (range)", [target(ratio(f"vllm:spec_decode_num_accepted_tokens_total{s()}",
                                                            f"vllm:spec_decode_num_draft_tokens_total{s()}", by,
                                                            "$__range", "increase"))],
              unit="percentunit", decimals=1, no_value="No drafts in range",
              desc="Accepted ÷ offered draft tokens from Strata's MTP layer."), 6, 4),
        (timeseries("Prompt cache reuse and MTP acceptance", [
            target(ratio(f"vllm:prefix_cache_hits_total{s()}", f"vllm:prefix_cache_queries_total{s()}", by),
                   "prompt cache reuse"),
            target(ratio(f"vllm:spec_decode_num_accepted_tokens_total{s()}",
                         f"vllm:spec_decode_num_draft_tokens_total{s()}", by), "MTP acceptance")],
            "percentunit", max_=1, decimals=1, interval=iv, no_value="No finished requests in this range"),
         12, 8),
        (timeseries("Expert cache hit and context use", [
            target(f"max by ({by}) (strata:last_hit_rate{s()})", "expert cache hit (last request)",
                   expect="optional"),
            target(f"max by ({by}) (vllm:kv_cache_usage_perc{s()})", "context used (running request)",
                   expect="live")], "percentunit", max_=1, decimals=1, step_line=True,
            no_value="Engine not running"), 12, 8),
        row("Hardware (Strata's own readings)"),
        (timeseries("GPU utilization", [target(f"max by (gpu) (strata:gpu_util{s()})", "GPU {{gpu}}",
                                               expect="live")], "percent", max_=100,
                    no_value="Engine not running"), 8, 8),
        (timeseries("GPU power", [target(f"max by (gpu) (strata:gpu_power_watts{s()})", "GPU {{gpu}}",
                                         expect="live")], "watt", desc="Red line = the 220 W per-card host cap.",
                    steps=(("green", None), ("red", 220)), threshold_style="line",
                    no_value="Engine not running"), 8, 8),
        (timeseries("GPU temperature", [target(f"max by (gpu) (strata:gpu_temp_celsius{s()})", "GPU {{gpu}}",
                                               expect="live")], "celsius", no_value="Engine not running"), 8, 8),
        (timeseries("GPU memory", [
            target(f"max by (gpu) (strata:gpu_mem_used_bytes{s()})", "used GPU {{gpu}}", expect="live"),
            target(f"max by (gpu) (strata:gpu_mem_total_bytes{s()})", "total GPU {{gpu}}", expect="live")],
            "bytes", desc="Near full by design: the expert cache takes the VRAM left after weights and KV.",
            no_value="Engine not running"), 8, 8),
        (timeseries("Node CPU and RAM (whole host)", [
            target(f"max by ({by}) (strata:cpu{s()}) / 100", "node CPU busy", expect="live"),
            target(f"max by ({by}) (strata:ram_used_bytes{s()}) / max by ({by}) (strata:ram_total_bytes{s()})",
                   "node RAM used", expect="live")], "percentunit", max_=1, decimals=0,
            desc="strata:cpu and strata:ram_* describe the whole GPU node, not the Strata pod.",
            no_value="Engine not running"), 8, 8),
        *[(p, 8, 8) for p in pod_resources(ns)],
    ]
    return dashboard(
        "strata-inference", "Strata Inference",
        "Strata only (namespace strata): engine state, live vs finished-request decode and prefill speed, "
        "latency, prompt/expert/context caches, MTP acceptance, GPUs, node CPU and RAM.",
        ["ai", "strata", "llm"], layout(panels), "now-6h", [model_variable(ns)])


# --------------------------------------------------------------------------- overview board

def overview_board():
    o = osel
    leg = "{{namespace}} · {{model_name}}"
    gen = f"vllm:generation_tokens_total{o()}"
    strata_new = ('(sum by (namespace, model_name) (rate(vllm:prefix_cache_queries_total{namespace="strata"}'
                  '[$__rate_interval])) - sum by (namespace, model_name) (rate(vllm:prefix_cache_hits_total'
                  '{namespace="strata"}[$__rate_interval])))')
    energy = ('sum by (namespace) (label_replace(increase(DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION'
              '{exported_namespace=~"vllm|strata"}[$__range]), "namespace", "$1", "exported_namespace", "(.+)"))'
              ' / 3600000')
    intro = text(
        "Both local engines, side by side. **vLLM** and **Strata** export the same `vllm:` metric names, so "
        "every query here groups by `namespace` (the engine) and `model_name`; nothing sums across engines. "
        "Engine details: **vLLM Inference**, **Strata Inference**.\n\n"
        "**Comparisons are history, not a benchmark:** each row is whatever that engine served in the range, "
        "with a different model, quantization, prompts and load. Strata's TTFT starts after its queue; vLLM's "
        "includes it. Controlled runs: `benchmarks/ai-realworld-load/`.\n\n"
        "**The gateway is separate.** Apps call LiteLLM; when the local engine is full or fails, LiteLLM can "
        "send the request to a paid cloud model, which never reaches these engines. The last row counts only "
        "what LiteLLM itself reports; details on **AI Gateway and Analytics**.")
    hist_cols = {}
    hist_targets = [
        target(f"sum by ({BY}) (increase(vllm:request_success_total{o()}[$__range]))"),
        target(f"sum by ({BY}) (increase({gen}[$__range]))"),
        target(f"sum by ({BY}) (increase(vllm:prompt_tokens_total{o()}[$__range])) / "
               f"sum by ({BY}) (increase(vllm:request_success_total{o()}[$__range]))"),
        target(f"sum by ({BY}) (increase({gen}[$__range])) / "
               f"sum by ({BY}) (increase(vllm:request_success_total{o()}[$__range]))"),
        target(ratio(f"vllm:inter_token_latency_seconds_count{o()}", f"vllm:inter_token_latency_seconds_sum{o()}",
                     BY, "$__range", "increase")),
        target(f"sum by ({BY}) (increase({gen}[$__range])) / $__range_s"),
        target(hist_range("vllm:time_to_first_token_seconds", "0.50", o(), BY)),
        target(hist_range("vllm:time_to_first_token_seconds", "0.95", o(), BY)),
        target(hist_range("vllm:e2e_request_latency_seconds", "0.50", o(), BY)),
        target(hist_range("vllm:e2e_request_latency_seconds", "0.95", o(), BY)),
        target(ratio(f"vllm:prefix_cache_hits_total{o()}", f"vllm:prefix_cache_queries_total{o()}", BY,
                     "$__range", "increase")),
        target(ratio(f"vllm:spec_decode_num_accepted_tokens_total{o()}",
                     f"vllm:spec_decode_num_draft_tokens_total{o()}", BY, "$__range", "increase"),
               expect="optional"),
        target(f"{energy} / on (namespace) group_right () "
               f"(sum by ({BY}) (increase({gen}[$__range])) / 1000)"),
    ]
    for ref, col in zip("ABCDEFGHIJKLM", [
            ("Requests", "short", 0), ("Generated tokens", "short", 0), ("Prompt tokens / request", "short", 0),
            ("Generated / request", "short", 0), ("Per-stream decode (1 ÷ mean ITL)", "tok/s", 1),
            ("Wall-clock gen (idle incl.)", "tok/s", 2), ("TTFT p50", "s", 2), ("TTFT p95", "s", 2),
            ("E2E p50", "s", 1), ("E2E p95", "s", 1), ("Prompt cache hit", "percentunit", 1),
            ("MTP acceptance", "percentunit", 1), ("GPU Wh / 1k gen tokens (idle incl.)", "short", 2)]):
        hist_cols[ref] = col
    panels = [
        (intro, 24, 5),
        row("Engines now"),
        (status_stat("vllm"), 4, 4),
        (status_stat("strata"), 4, 4),
        (stat("Model per engine", [target(f"max by ({BY}) (vllm:num_requests_running{o()})", leg, expect="live")],
              text_mode="name", no_value="No engine running",
              desc="model_name each running engine reports."), 4, 4),
        (stat("Requests running", [target(f"sum by ({BY}) (vllm:num_requests_running{o()})", "{{namespace}}",
                                          expect="live")], no_value="No engine running"), 4, 4),
        (stat("Requests waiting", [target(f"sum by ({BY}) (vllm:num_requests_waiting{o()})", "{{namespace}}",
                                          expect="live")], no_value="No engine running",
              steps=(("green", None), ("orange", 1))), 4, 4),
        (stat("Generated tokens/s now", [target(f"sum by ({BY}) (rate({gen}[$__rate_interval]))",
                                                "{{namespace}}", expect="live")], unit="tok/s", decimals=1,
              no_value="No engine running", desc="Wall clock, idle time counts as 0."), 4, 4),
        row("History by engine and model (selected range)"),
        (table("Per-engine history", hist_targets, hist_cols, no_value="No data in range",
               desc="One row per engine and model over the selected range. Different models, prompts and load: "
                    "read it as history, not a benchmark. Per-stream decode = generated tokens ÷ decode time. "
                    "GPU Wh counts the engine's cards for the whole range, idle included; if one engine served "
                    "two models in the range both rows share that energy."), 24, 7),
        row("Speed over time, by engine"),
        (timeseries("Per-stream decode speed (1 ÷ mean inter-token latency)", [target(ratio(
            f"vllm:inter_token_latency_seconds_count{o()}", f"vllm:inter_token_latency_seconds_sum{o()}", BY), leg)],
            "tok/s", decimals=1, interval="2m", no_value="No finished requests in this range",
            desc="What one stream sees while generating, token-weighted over the window. Same definition on "
                 "both engines (decode time ÷ token gaps)."), 12, 8),
        (timeseries("Generated tokens/s (wall clock, idle included)", [target(
            f"sum by ({BY}) (rate({gen}[$__rate_interval]))", leg)], "tok/s", decimals=1, interval="2m",
            no_value="No traffic in this range",
            desc="Load, not speed: it drops whenever the engine waits for requests."), 12, 8),
        (timeseries("Prefill speed", [
            target(f'sum by ({BY}) (rate(vllm:prompt_tokens_by_source_total{{namespace="vllm", '
                   f'source="local_compute"}}[$__rate_interval])) / sum by ({BY}) '
                   '(rate(vllm:request_prefill_time_seconds_sum{namespace="vllm"}[$__rate_interval]))', leg),
            target(f'{strata_new} / sum by ({BY}) (rate(strata:totals_prompt_seconds_total{{namespace="strata"}}'
                   '[$__rate_interval]))', leg)], "tok/s", decimals=0, interval="2m",
            no_value="No finished requests in this range",
            desc="Computed prompt tokens ÷ prefill time. vLLM uses its prefill histogram, Strata its own "
                 "prompt-reading clock: close, not identical."), 12, 8),
        (timeseries("Time to first token", [
            target(hist("vllm:time_to_first_token_seconds", "0.50", o(), BY), "p50 " + leg),
            target(hist("vllm:time_to_first_token_seconds", "0.95", o(), BY), "p95 " + leg)], "s", decimals=2,
            interval="2m", no_value="No finished requests in this range",
            desc="vLLM includes queue wait; Strata starts after its queue."), 12, 8),
        (timeseries("End-to-end request time p95", [target(hist("vllm:e2e_request_latency_seconds", "0.95", o(),
                                                                 BY), leg)], "s", decimals=1, interval="2m",
                    no_value="No finished requests in this range"), 12, 8),
        (timeseries("Running and waiting", [
            target(f"sum by ({BY}) (vllm:num_requests_running{o()})", "running " + leg, expect="live"),
            target(f"sum by ({BY}) (vllm:num_requests_waiting{o()})", "waiting " + leg, expect="live")],
            "short", decimals=0, step_line=True, no_value="No engine running"), 12, 8),
        row("Caches and MTP, by engine"),
        (timeseries("Prompt (prefix) cache hit", [target(ratio(f"vllm:prefix_cache_hits_total{o()}",
                                                              f"vllm:prefix_cache_queries_total{o()}", BY), leg)],
                    "percentunit", max_=1, decimals=1, interval="2m", no_value="No prompts in this range",
                    desc="vLLM: GPU KV prefix blocks. Strata: tokens kept from an earlier turn. Same idea, "
                         "different cache."), 12, 8),
        (timeseries("MTP draft acceptance", [target(ratio(f"vllm:spec_decode_num_accepted_tokens_total{o()}",
                                                         f"vllm:spec_decode_num_draft_tokens_total{o()}", BY), leg,
                                                   expect="optional")],
                    "percentunit", max_=1, decimals=1, interval="2m", no_value="No drafts in this range",
                    desc="Only engines running speculative decoding appear; vLLM runs with MTP off."), 12, 8),
        row("GPUs by engine (DCGM)"),
        (timeseries("GPU power, both cards", [target(
            'sum by (exported_namespace) (DCGM_FI_DEV_POWER_USAGE{exported_namespace=~"vllm|strata"})',
            "{{exported_namespace}}", expect="live")], "watt", no_value="No engine holds a GPU",
            desc="Sum of the cards each engine holds (cap 220 W each)."), 8, 8),
        (timeseries("GPU utilization, mean of cards", [target(
            'avg by (exported_namespace) (DCGM_FI_DEV_GPU_UTIL{exported_namespace=~"vllm|strata"})',
            "{{exported_namespace}}", expect="live")], "percent", max_=100, no_value="No engine holds a GPU"),
         8, 8),
        (timeseries("GPU memory used, both cards", [target(
            'sum by (exported_namespace) (DCGM_FI_DEV_FB_USED{exported_namespace=~"vllm|strata"}) * 1024 * 1024',
            "{{exported_namespace}}", expect="live")], "bytes", no_value="No engine holds a GPU"), 8, 8),
        row("Gateway context (LiteLLM, not the engines)"),
        (table("LiteLLM fallbacks to another model (range)", [target(
            "sum by (requested_model, fallback_model, exception_status) "
            "(increase(litellm_deployment_successful_fallbacks_total[$__range])) > 0", expect="optional")],
            {"A": ("Fallbacks", "short", 0)}, no_value="No fallbacks in range",
            desc="LiteLLM's successful fallbacks: the first model failed (status shown; 429 = its parallel limit) "
                 "and another model answered. Those requests did not run on a local engine."), 12, 6),
        (text("**Where the other traffic went:** spend and which backend answered are on **AI Gateway and "
              "Analytics** (`/d/ai-gateway-analytics`); per-request traces in Langfuse. GPU cards and the pods "
              "holding them: **GPU Overview** (`/d/gpu-overview`)."), 12, 6),
    ]
    # the fallback table keys on its own labels, not namespace/model
    fallback = panels[-2][0]
    fallback["transformations"][1]["options"]["indexByName"] = {
        "requested_model": 0, "fallback_model": 1, "exception_status": 2, "Value #A": 3}
    fallback["transformations"][1]["options"]["renameByName"] = {
        "requested_model": "Requested", "fallback_model": "Answered by", "exception_status": "First error",
        "Value #A": "Fallbacks"}
    return dashboard(
        OVERVIEW_UID, "Local LLM Engines",
        "vLLM and Strata side by side, always split by engine and model: state, speed, latency, caches, GPUs, "
        "range history, and LiteLLM fallbacks as gateway context.",
        ["ai", "vllm", "strata", "llm"], layout(panels), "now-7d", refresh="1m")


# --------------------------------------------------------------------------- output

BOARDS = {"vllm-inference.json": vllm_board, "strata-inference.json": strata_board,
          "llm-engines.json": overview_board}


def strip(obj):
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def build():
    """{filename: dashboard with private `_expect` keys}."""
    return {name: fn() for name, fn in BOARDS.items()}


def expectations(boards=None):
    """[(uid, panel title, refId, expr, expect)] for the live validator."""
    out = []
    for board in (boards or build()).values():
        for panel in board["panels"]:
            for t in panel.get("targets", []):
                out.append((board["uid"], panel["title"], t["refId"], t["expr"], t["_expect"]))
    return out


def render(board):
    return json.dumps(strip(board), indent=2, ensure_ascii=False) + "\n"


def promtool_fixture():
    """promql_expr_test cases for the status expressions (one per state)."""
    def series(ns, replicas=None, up=None, wait=None):
        e = ENGINES[ns]
        out = []
        if replicas is not None:
            out.append({"series": f'kube_deployment_spec_replicas{{namespace="{ns}", deployment="{e["deployment"]}"}}',
                        "values": f"{replicas}x10"})
        if up is not None:
            out.append({"series": f'up{{namespace="{ns}", job="{e["job"]}", pod="p"}}', "values": f"{up}x10"})
        if wait is not None:
            if ns == "vllm":
                out.append({"series": 'vllm:engine_sleep_state{namespace="vllm", sleep_state="awake", engine="0"}',
                            "values": f"{0 if wait else 1}x10"})
            else:
                out.append({"series": 'strata:live_state{namespace="strata", state="unloaded"}',
                            "values": f"{1 if wait else 0}x10"})
        return out

    cases = {"not deployed": ({}, STATUS_ABSENT), "parked": ({"replicas": 0}, STATUS_PARKED),
             "parked with stale up": ({"replicas": 0, "up": 1}, STATUS_PARKED),
             "pending pod": ({"replicas": 1}, STATUS_DOWN), "scrape failing": ({"replicas": 1, "up": 0}, STATUS_DOWN),
             "serving": ({"replicas": 1, "up": 1, "wait": False}, STATUS_SERVING),
             "asleep or loading": ({"replicas": 1, "up": 1, "wait": True}, STATUS_WAIT)}
    tests = []
    for ns in ENGINES:
        expr = status_expr(ns, STATUS_WAIT_RULES[ns]).replace("\n  ", " ")
        for name, (kw, code) in cases.items():
            tests.append({"name": f"{ns}: {name}", "interval": "1m", "input_series": series(ns, **kw),
                          "promql_expr_test": [{"expr": expr, "eval_time": "5m",
                                                 "exp_samples": [{"labels": "{}", "value": code}]}]})
    return {"rule_files": ["inference-status.rules.yaml"], "evaluation_interval": "1m", "tests": tests}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if committed JSON differs")
    parser.add_argument("--promtool-tests", type=Path, metavar="DIR", help="write promtool fixtures to DIR")
    args = parser.parse_args()
    boards = build()
    if args.promtool_tests:
        args.promtool_tests.mkdir(parents=True, exist_ok=True)
        (args.promtool_tests / "inference-status.rules.yaml").write_text("groups: []\n")
        (args.promtool_tests / "inference-status.test.yaml").write_text(json.dumps(promtool_fixture(), indent=2))
        return 0
    stale = []
    for name, board in boards.items():
        path, out = OUT_DIR / name, render(board)
        if args.check:
            if not path.exists() or path.read_text() != out:
                stale.append(name)
        else:
            path.write_text(out)
    if stale:
        print(f"ERROR: regenerate with scripts/generate-inference-dashboards.py: {', '.join(stale)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
