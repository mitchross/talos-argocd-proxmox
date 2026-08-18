#!/usr/bin/env python3
"""Baseline A report.

Every number is tagged MEASURED or DERIVED. That distinction is the whole point
of this run: the single-vs-dual GPU decision rests on peak real context, and a
derived number that looks measured would quietly corrupt it.

  MEASURED  read directly from a counter/gauge/log the server or client emitted
  DERIVED   computed from those (e.g. kv_usage_perc x capacity), stated with its
            formula, and given as a RANGE when the source is a histogram bucket

Usage: report.py <run-dir> [--pi-session <path>]
"""
import sys, os, json, re, glob
from collections import defaultdict

M, D = "MEASURED", "DERIVED"


def parse_ticks(path):
    """metrics.stream -> [(epoch, {metric_key: value})]"""
    ticks, cur, ts = [], None, None
    if not os.path.exists(path):
        return ticks
    for line in open(path, errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("===TICK"):
            if cur is not None:
                ticks.append((ts, cur))
            p = line.split()
            ts = int(p[2]) if len(p) > 2 and p[2].isdigit() else None
            cur = {}
        elif cur is not None and line.startswith("vllm:"):
            try:
                key, val = line.rsplit(" ", 1)
                cur[key] = float(val)
            except ValueError:
                pass
    if cur:
        ticks.append((ts, cur))
    return ticks


def g(sample, prefix):
    """First metric whose name starts with prefix (labels vary)."""
    for k, v in sample.items():
        if k.startswith(prefix):
            return v
    return None


def hist_buckets(sample, name):
    """[(le, cumulative_count)] sorted ascending for a histogram."""
    out = []
    for k, v in sample.items():
        if k.startswith(name + "_bucket"):
            m = re.search(r'le="([^"]+)"', k)
            if m:
                le = float("inf") if m.group(1) in ("+Inf", "Inf") else float(m.group(1))
                out.append((le, v))
    return sorted(out)


def bucket_range(before, after):
    """Which bucket(s) gained count between two histogram snapshots.

    Returns list of (lo, hi, n) — a request that completed landed in (lo, hi].
    This is the ONLY server-side per-request size signal vLLM exposes here, and
    it is coarse (…20k, 50k, 100k, 200k, Inf), so results are ranges by nature.
    """
    b, a = dict(before), dict(after)
    les = sorted(a)
    out, prev_le = [], 0.0
    for le in les:
        d = a.get(le, 0) - b.get(le, 0)
        # cumulative: subtract everything already attributed to smaller buckets
        lower = sum(x[2] for x in out)
        n = d - lower
        if n > 0:
            out.append((prev_le, le, n))
        prev_le = le
    return out


def fmt(n):
    return f"{int(n):,}" if n is not None else "–"


def section(t):
    print(f"\n{'='*78}\n{t}\n{'='*78}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    run = sys.argv[1].rstrip("/")
    pi_session = None
    if "--pi-session" in sys.argv:
        pi_session = sys.argv[sys.argv.index("--pi-session") + 1]

    ctx = {}
    if os.path.exists(f"{run}/context.env"):
        for line in open(f"{run}/context.env"):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                ctx[k] = v

    cap = 313367
    cc = f"{run}/cache-config.txt"
    if os.path.exists(cc):
        m = re.search(r'kv_cache_size_tokens="(\d+)"', open(cc).read())
        if m:
            cap = int(m.group(1))

    ticks = parse_ticks(f"{run}/metrics.stream")
    if not ticks:
        print("no metric ticks captured — was the collector running?")
        sys.exit(1)

    print(f"{ctx.get('label', 'run').upper()} — {os.path.basename(run)}")
    print(f"pod={ctx.get('pod','?')}  node={ctx.get('node','?')}")
    print(f"window={ctx.get('run_started_utc','?')} .. {ctx.get('run_ended_utc','in progress')}")
    print(f"KV capacity ceiling = {cap:,} tokens   [{M}, from engine cache_config_info]")
    print(f"gpu sampling source = {ctx.get('gpu_source','?')}")
    print(f"ticks captured = {len(ticks)} (~2s apart)")

    # ---------------- headline numbers -------------------------------------
    section("THE FOUR NUMBERS")

    # NB: every metric key carries Prometheus labels
    # (vllm:num_requests_running{engine="0",model_name="..."}), so these MUST go
    # through the prefix helper. Exact-key lookups silently return 0 and make a
    # loaded run look idle.
    resident = [(t, (g(s, "vllm:kv_cache_usage_perc") or 0.0) * cap) for t, s in ticks]
    peak_res = max((r for _, r in resident), default=0)
    peak_t = max(resident, key=lambda x: x[1])[0] if resident else None

    print(f"\n4. PEAK SIMULTANEOUS RESIDENT CONTEXT : {fmt(peak_res)} tokens   [{D}]")
    print(f"   formula: max(vllm:kv_cache_usage_perc) x {cap:,}")
    print(f"   = {peak_res/cap*100:.1f}% of the measured KV pool" if cap else "")
    print(f"   NOTE: KV occupancy includes blocks retained by the prefix cache,")
    print(f"         so this is an upper bound on live request context.")

    # Per-workload: histogram bucket deltas across the whole run.
    first, last = ticks[0][1], ticks[-1][1]
    hb = bucket_range(hist_buckets(first, "vllm:request_prompt_tokens"),
                      hist_buckets(last, "vllm:request_prompt_tokens"))
    print(f"\n   completed-request prompt sizes this run (histogram buckets) [{D}, range]:")
    if hb:
        for lo, hi, n in hb:
            hs = "inf" if hi == float("inf") else fmt(hi)
            print(f"     {int(n):>3} request(s) with prompt in ({fmt(lo)}, {hs}] tokens")
    else:
        print("     (none completed in window)")

    # Pi: exact, from its own session file.
    pi_peak = None
    if pi_session and os.path.exists(pi_session):
        best = 0
        for line in open(pi_session, errors="replace"):
            try:
                o = json.loads(line)
            except Exception:
                continue
            u = o.get("usage") or (o.get("message") or {}).get("usage") or {}
            v = u.get("input")
            if isinstance(v, (int, float)):
                best = max(best, int(v))
        pi_peak = best or None

    print(f"\n2. PI PEAK PROMPT/CONTEXT             : "
          f"{fmt(pi_peak) if pi_peak else 'run pi, then re-run with --pi-session'}"
          f"   [{M}, pi session usage.input]")
    print(f"1. PERPLEXICA PEAK PROMPT/CONTEXT     : see bucket table above   [{D}]")
    print(f"   attribution: Pi is measured exactly, Deal Scout is ~10k, so the")
    print(f"   largest remaining bucket is Perplexica by elimination.")
    print(f"3. DEAL SCOUT DIGEST PROMPT           : smallest bucket above    [{D}]")
    print(f"   exact value: tokenize the digest prompt via /tokenize post-run.")

    # ---------------- scheduling / preemption ------------------------------
    section("SCHEDULING — PREEMPTION IS RECOMPUTE-ONLY IN vLLM V1")
    runq = [(t, g(s, "vllm:num_requests_running") or 0) for t, s in ticks]
    waitq = [(t, g(s, "vllm:num_requests_waiting{") or 0) for t, s in ticks]
    pre = [(t, g(s, "vllm:num_preemptions_total") or 0) for t, s in ticks]

    print(f"max concurrent RUNNING sequences : {int(max(v for _,v in runq)):>4}   [{M}]")
    print(f"max WAITING sequences            : {int(max(v for _,v in waitq)):>4}   [{M}]")
    print(f"peak KV utilisation              : {max((g(s,'vllm:kv_cache_usage_perc') or 0) for _,s in ticks)*100:>7.1f}%  [{M}]")
    total_pre = (pre[-1][1] - pre[0][1]) if pre else 0
    print(f"preemptions during run           : {int(total_pre):>4}   [{M}]")

    peak_conc = int(max((v for _, v in runq), default=0))
    overlapped = sum(1 for _, v in runq if v >= 2)
    print(f"ticks with >=2 running           : {overlapped:>4} of {len(ticks)}   [{M}]")
    if peak_conc < 2:
        print("  !! the workloads never overlapped — the run does not test concurrency.")
        print("     Re-run with tighter launch spacing.")

    if total_pre > 0:
        print("\n  PREEMPTION FORENSICS (recompute restarts prefill from token 0):")
        for i in range(1, len(ticks)):
            d = (g(ticks[i][1], "vllm:num_preemptions_total") or 0) - \
                (g(ticks[i-1][1], "vllm:num_preemptions_total") or 0)
            if d > 0:
                kvb = g(ticks[i-1][1], "vllm:kv_cache_usage_perc") or 0
                print(f"   +{int(d)} at t={ticks[i][0]}  KV just before = {kvb*100:.1f}% "
                      f"({fmt(kvb*cap)} tokens resident)   [{M}]")
        print("   grep vllm.log for the surrounding engine lines to attribute a request id.")
    else:
        print("\n  No preemptions — no recompute stalls to account for.")

    # ---------------- latency ----------------------------------------------
    section("LATENCY")
    for label, name in (("TTFT", "vllm:time_to_first_token_seconds"),
                        ("TPOT", "vllm:request_time_per_output_token_seconds"),
                        ("E2E ", "vllm:e2e_request_latency_seconds"),
                        ("queue", "vllm:request_queue_time_seconds"),
                        ("prefill", "vllm:request_prefill_time_seconds")):
        s0, c0 = g(first, name + "_sum"), g(first, name + "_count")
        s1, c1 = g(last, name + "_sum"), g(last, name + "_count")
        if None in (s0, c0, s1, c1) or (c1 - c0) <= 0:
            print(f"{label:<8}: no completions in window")
            continue
        print(f"{label:<8}: mean {(s1-s0)/(c1-c0):7.3f}s over {int(c1-c0)} requests   [{D}, sum/count delta]")

    # ---------------- throughput / cache ------------------------------------
    section("THROUGHPUT & CACHE")
    for label, name in (("prompt tokens processed", "vllm:prompt_tokens_total"),
                        ("generation tokens", "vllm:generation_tokens_total"),
                        ("prompt tokens from cache", "vllm:prompt_tokens_cached_total")):
        a, b = g(first, name), g(last, name)
        if a is not None and b is not None:
            print(f"{label:<26}: {fmt(b-a):>12}   [{M}, counter delta]")
    pq0, ph0 = g(first, "vllm:prefix_cache_queries_total"), g(first, "vllm:prefix_cache_hits_total")
    pq1, ph1 = g(last, "vllm:prefix_cache_queries_total"), g(last, "vllm:prefix_cache_hits_total")
    if None not in (pq0, ph0, pq1, ph1) and (pq1 - pq0) > 0:
        print(f"{'prefix cache hit rate':<26}: {(ph1-ph0)/(pq1-pq0)*100:>11.1f}%   [{D}, hits/queries delta]")

    # ---------------- outcomes ----------------------------------------------
    section("REQUEST OUTCOMES")
    for k in sorted(last):
        if k.startswith("vllm:request_success_total"):
            r = re.search(r'finished_reason="([^"]+)"', k)
            d = last[k] - first.get(k, 0)
            if d:
                flag = "  <-- CONTEXT LIMIT / TRUNCATION" if r and r.group(1) == "length" else ""
                print(f"  {r.group(1) if r else '?':<12}: {int(d):>4}{flag}   [{M}]")

    # ---------------- GPUs ---------------------------------------------------
    section("PER-GPU (was one card doing less work?)")
    per = defaultdict(lambda: defaultdict(list))
    gp = f"{run}/gpu.csv"
    if os.path.exists(gp):
        for line in open(gp, errors="replace"):
            p = [x.strip() for x in line.split(",")]
            if len(p) < 9 or not p[1].isdigit():
                continue
            i = int(p[1])
            for key, idx in (("vram", 2), ("util", 4), ("power", 6), ("temp", 8)):
                try:
                    per[i][key].append(float(p[idx]))
                except ValueError:
                    pass
    for i in sorted(per):
        v, u, w, t = per[i]["vram"], per[i]["util"], per[i]["power"], per[i]["temp"]
        if not v:
            continue
        print(f"GPU{i}: VRAM peak {max(v):>7.0f} MiB | util avg {sum(u)/len(u):5.1f}% peak {max(u):5.1f}% "
              f"| power avg {sum(w)/len(w):5.1f}W peak {max(w):5.1f}W | temp peak {max(t):4.1f}C   [{M}]")
    if len(per) == 2 and per[0]["util"] and per[1]["util"]:
        a, b = sum(per[0]["util"])/len(per[0]["util"]), sum(per[1]["util"])/len(per[1]["util"])
        if max(a, b) > 0:
            print(f"\nutilisation imbalance: {abs(a-b)/max(a,b)*100:.1f}%   [{D}]")
            if min(a, b) < 1.0:
                print("  One card is idle — single-card run, so 100% imbalance is expected.")
            else:
                print("  TP over PCIe with no NVLink — large sustained imbalance would")
                print("  point at NCCL/PCIe stalls rather than genuine idle.")

    # ---------------- health -------------------------------------------------
    section("POD HEALTH")
    pp = f"{run}/pod.csv"
    if os.path.exists(pp):
        rows = [l.strip() for l in open(pp) if l.strip()]
        if rows:
            restarts = set()
            for r in rows:
                f_ = r.split(",")
                if len(f_) > 3 and f_[3].isdigit():
                    restarts.add(f_[3])
            print(f"samples={len(rows)}  restart counts seen: {sorted(restarts) or 'n/a'}   [{M}]")
            print(f"last: {rows[-1]}")
    for pat, lbl in ((r"OOM|OutOfMemory", "OOM"),
                     (r"context length|maximum context|too long", "CONTEXT-LIMIT"),
                     (r"Cache allocation|cannot allocate", "CACHE-ALLOC"),
                     (r"Preempt", "PREEMPT-LOG")):
        lp = f"{run}/vllm.log"
        if os.path.exists(lp):
            n = len(re.findall(pat, open(lp, errors="replace").read(), re.I))
            if n:
                print(f"  vllm.log matches for {lbl}: {n}")

    print("\n" + "=" * 78)
    print("Reminder: peak resident context is DERIVED (kv% x capacity) and includes")
    print("prefix-cache-retained blocks. Pi's figure is the only exact per-workload")
    print("context number available without changing production app behaviour.")


if __name__ == "__main__":
    main()
