#!/usr/bin/env python3
"""Run every inference-dashboard query against a live Prometheus and classify the results.

Read-only: instant queries only. Grafana variables are substituted ($model = All). Each query runs in three
passes: now (Grafana-sized 5m rate window), now with a 1h window, and at the last moment vLLM reported
samples ("vllm era"), so a parked engine's panels are proven against its own history. Writes a JSON
report and prints a summary; exits 1 on query errors, isolation leaks or broken status semantics.
"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts/generate-inference-dashboards.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

RANGE = "24h"


def query(prom, expr, at):
    url = f"{prom}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": f"{at:.3f}"})
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = json.load(exc)
    if body.get("status") != "success":
        return {"error": body.get("error", "unknown")}
    data = body["data"]
    result = data["result"] if data["resultType"] == "vector" else [{"metric": {}, "value": data["result"]}]
    return {"samples": [{"labels": r["metric"], "value": float(r["value"][1])} for r in result]}


def substitute(expr, rate):
    seconds = {"h": 3600, "m": 60, "d": 86400}[RANGE[-1]] * int(RANGE[:-1])
    return (expr.replace("$__rate_interval", rate).replace("$__interval", "1m")
            .replace("$__range_s", str(seconds)).replace("$__range", RANGE).replace("$model", ".+"))


def engine_of(uid, expr):
    if uid in ("vllm-inference", "strata-inference"):
        return uid.split("-")[0]
    if "litellm_" in expr:
        return "gateway"
    pinned = [ns for ns in gen.ENGINES if f'namespace="{ns}"' in expr]
    return pinned[0] if len(pinned) == 1 else "both"


def classify(res):
    if "error" in res:
        return "error"
    if not res["samples"]:
        return "empty"
    return "finite" if any(math.isfinite(s["value"]) for s in res["samples"]) else "non-finite"


def leaks(engine, res):
    """Isolation: samples must belong to the board's engine; overview samples must say which engine."""
    bad = []
    models = {k: re.compile(v["model_regex"]) for k, v in gen.ENGINES.items()}
    for s in res.get("samples", []):
        ns, model = s["labels"].get("namespace") or s["labels"].get("exported_namespace"), s["labels"].get("model_name")
        if engine in gen.ENGINES:
            if ns and ns != engine:
                bad.append(s["labels"])
            other = [k for k in gen.ENGINES if k != engine][0]
            if model and models[other].search(model):
                bad.append(s["labels"])
        elif engine == "both" and s["labels"] and not ns:
            bad.append(s["labels"])
    return bad


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prometheus", default="http://kube-prometheus-stack-prometheus.prometheus-stack.svc:9090")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    now = time.time()
    era = query(args.prometheus, 'max(max_over_time(timestamp(vllm:generation_tokens_total{namespace="vllm"})[15d:5m]))',
                now)
    era_t = era["samples"][0]["value"] if era.get("samples") else None
    passes = {"now-5m": (now, "5m"), "now-1h": (now, "1h")}
    if era_t:
        passes["vllm-era-1h"] = (era_t, "1h")
    live = {ns: classify(query(args.prometheus, f'up{{namespace="{ns}", job="{e["job"]}"}} == 1', now)) == "finite"
            for ns, e in gen.ENGINES.items()}

    rows, failures = [], []
    items = gen.expectations()
    for board in gen.build().values():
        for var in board["templating"]["list"]:
            m = re.match(r"label_values\((.*), (\w+)\)$", var["query"]["query"])
            items.append((board["uid"], f"variable ${var['name']}", "-", f"group by ({m[2]}) ({m[1]})", "traffic"))
    for uid, title, ref, expr, expect in items:
        engine = engine_of(uid, expr)
        row = {"dashboard": uid, "panel": title, "ref": ref, "expect": expect, "engine": engine, "passes": {}}
        for name, (at, rate) in passes.items():
            res = query(args.prometheus, substitute(expr, rate), at)
            row["passes"][name] = {"result": classify(res), "series": len(res.get("samples", [])),
                                   "values": [round(s["value"], 4) for s in res.get("samples", [])[:4]],
                                   **({"error": res["error"]} if "error" in res else {})}
            if "error" in res:
                failures.append(f"{uid} / {title} {ref} [{name}]: {res['error']}")
            if leak := leaks(engine, res):
                failures.append(f"{uid} / {title} {ref} [{name}]: engine leak {leak[:2]}")
            if expect == "status" and (row["passes"][name]["series"] != 1
                                       or row["passes"][name]["result"] != "finite"):
                failures.append(f"{uid} / {title} [{name}]: status must return exactly one value")
        # what an empty result means, given the engine's live state
        served_now = engine in gen.ENGINES and live[engine]
        verdict = []
        for name, p in row["passes"].items():
            if p["result"] != "empty":
                continue
            if engine in gen.ENGINES and not name.startswith("vllm-era") and not served_now:
                verdict.append(f"{name}: expected empty (engine parked now)")
            elif engine == "strata" and name.startswith("vllm-era"):
                verdict.append(f"{name}: expected empty (Strata not deployed then)")
            elif expect == "optional":
                verdict.append(f"{name}: allowed empty (optional / unsupported metric)")
            elif expect == "live" and (served_now or name.startswith("vllm-era")):
                verdict.append(f"{name}: UNEXPECTED empty for a live gauge")
            else:
                verdict.append(f"{name}: empty (no finished requests in window)")
        row["notes"] = verdict
        if any("UNEXPECTED" in v for v in verdict):
            failures.append(f"{uid} / {title} {ref}: " + "; ".join(v for v in verdict if "UNEXPECTED" in v))
        rows.append(row)

    status_now = {r["dashboard"] + " " + r["panel"]: r["passes"]["now-5m"]["values"]
                  for r in rows if r["expect"] == "status"}
    summary = {"prometheus": args.prometheus, "evaluated_at": now, "vllm_era_at": era_t, "range": RANGE,
               "engines_up_now": live, "status_now": status_now, "queries": len(rows),
               "results": {name: {k: sum(1 for r in rows if r["passes"].get(name, {}).get("result") == k)
                                  for k in ("finite", "empty", "non-finite", "error")} for name in passes},
               "failures": failures}
    args.report.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
