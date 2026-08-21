#!/usr/bin/env python3
"""NInfer candidate run report — parses the schema-v8 request-log JSONL.

Same honesty rules as report.py: every number is tagged MEASURED or DERIVED.
Metrics that exist in vLLM but have no NInfer equivalent are printed as N/A —
never fabricated (there is no KV-usage gauge, and no preemption concept: NInfer
admission reserves the full prompt+output entitlement and queues instead).

Usage: report-ninfer.py <run-dir>
"""
import json, os, sys
from collections import Counter

M, D = "MEASURED", "DERIVED"


def load_events(path):
    evs = []
    if not os.path.exists(path):
        return evs
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            evs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return evs


def fmt(n):
    return f"{n:,.3f}" if isinstance(n, float) else f"{n:,}" if isinstance(n, int) else str(n)


def section(t):
    print(f"\n=== {t} " + "=" * max(0, 60 - len(t)))


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: report-ninfer.py <run-dir>")
    run = sys.argv[1]

    window = [e for e in load_events(os.path.join(run, "requests.jsonl.stream"))]
    full = load_events(os.path.join(run, "requests.jsonl"))
    starts = [e for e in full if e.get("event") == "server_start"] or \
             [e for e in full if "server_start" in json.dumps(e)[:200]]

    section("Server (from server_start, full log)")
    if starts:
        s = starts[-1]
        for key in ("artifact", "target", "weights", "kv", "engine", "argv", "cuda", "gpu"):
            for k, v in s.items():
                if key in k.lower():
                    print(f"  {k}: {json.dumps(v)[:300]}  [{M}]")
    else:
        print("  no server_start event captured — KV sizing ledger unavailable (N/A)")

    done = [e for e in window if e.get("event") == "request_done"]
    errs = [e for e in window if e.get("event") == "request_error"]

    section(f"Requests in window: {len(done)} done, {len(errs)} errors")
    rows = []
    for e in done:
        t = e.get("timings_seconds", {}) or {}
        spec = (t.get("speculative") or e.get("speculative") or {})
        prompt = e.get("prompt_tokens") or e.get("tokens", {}).get("prompt")
        comp = e.get("completion_tokens") or e.get("tokens", {}).get("completion")
        cache = e.get("cache_tokens") or e.get("tokens", {}).get("cache")
        row = {
            "prompt": prompt, "completion": comp, "cache": cache,
            "ttft": t.get("ttft"), "prefill": t.get("prefill"),
            "decode": t.get("decode"), "vision": t.get("vision"),
            "total": t.get("total"),
            "finish": e.get("finish_reason"),
            "reuse_path": e.get("prefix_reuse_path"),
            "drafted": spec.get("drafted_tokens"),
            "accepted": spec.get("accepted_tokens"),
        }
        if comp and t.get("decode"):
            row["decode_tps"] = round(comp / t["decode"], 2)
        rows.append(row)

    if rows:
        hdr = ["prompt", "cache", "completion", "ttft", "prefill", "decode",
               "decode_tps", "total", "finish", "reuse_path"]
        print("  " + " | ".join(f"{h:>10}" for h in hdr))
        for r in rows:
            print("  " + " | ".join(f"{fmt(r.get(h)) if r.get(h) is not None else '-':>10}" for h in hdr))
        print(f"  [{M}] tokens/seconds are engine-reported; decode_tps is [{D}] completion/decode_s")

        n = len(rows)
        mean = lambda k: sum(r[k] for r in rows if r.get(k) is not None) / max(1, sum(1 for r in rows if r.get(k) is not None))
        print(f"\n  TTFT mean        : {mean('ttft'):.3f}s  [{M}]")
        print(f"  prefill mean     : {mean('prefill'):.3f}s  [{M}]")
        print(f"  decode tok/s mean: {mean('decode_tps'):.2f}  [{D}]")
        drafted = sum(r["drafted"] or 0 for r in rows)
        accepted = sum(r["accepted"] or 0 for r in rows)
        if drafted:
            print(f"  MTP acceptance   : {100*accepted/drafted:.1f}% ({accepted:,}/{drafted:,})  [{M}]")
        cache_t = sum(r["cache"] or 0 for r in rows)
        prompt_t = sum(r["prompt"] or 0 for r in rows)
        if prompt_t:
            print(f"  prefix reuse     : {100*cache_t/prompt_t:.1f}% of prompt tokens ({cache_t:,}/{prompt_t:,})  [{M}]")
        print(f"  reuse paths      : {dict(Counter(r['reuse_path'] for r in rows))}  [{M}]")
        print(f"  finish reasons   : {dict(Counter(r['finish'] for r in rows))}  [{M}]")
    for e in errs:
        print(f"  ERROR: {json.dumps(e)[:300]}")

    section("GPU (per index — the run's context.env says which card is NInfer's)")
    gpath = os.path.join(run, "gpu.csv")
    if os.path.exists(gpath):
        peak = {}
        for line in open(gpath, errors="replace"):
            p = [x.strip() for x in line.split(",")]
            if len(p) < 8:
                continue
            try:
                idx = p[1]
                d = peak.setdefault(idx, {"mem": 0.0, "util": 0.0, "power": 0.0})
                d["mem"] = max(d["mem"], float(p[2]))
                d["util"] = max(d["util"], float(p[4]))
                d["power"] = max(d["power"], float(p[6]))
            except ValueError:
                continue
        for idx, d in sorted(peak.items()):
            print(f"  GPU {idx}: peak {d['mem']:.0f} MiB, peak util {d['util']:.0f}%, "
                  f"peak power {d['power']:.0f} W  [{M}]")
    else:
        print("  no gpu.csv")

    section("Not comparable to vLLM (stated, not fabricated)")
    print("  kv_cache_usage_perc equivalent : N/A (no gauge; KV ledger only at server_start)")
    print("  preemptions                    : N/A concept (FIFO full-entitlement admission;")
    print("                                   overload -> 429 server_overloaded / 503 queue_timeout —")
    print("                                   count those in ninfer.log / request_error instead)")
    print("  Prometheus histograms          : N/A (per-request JSONL timings instead)")


if __name__ == "__main__":
    main()
