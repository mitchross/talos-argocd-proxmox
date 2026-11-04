#!/usr/bin/env python3
"""Send C different chat requests at once and time each one (stdlib only, thinking off).

Measures what a burst of apps sees from one OpenAI-compatible endpoint: per-request TTFT (includes the time a request
waits in the server's queue), per-request decode tok/s, and aggregate tok/s (all completion tokens / wall time of the
round).  Each request gets its own topic and a unique first line so no prompt-cache prefix is shared.

  python3 tools/concurrency_probe.py --base-url http://127.0.0.1:18080/v1 --model qwen3.8-flash-next-iq3_s \
      --levels 1,2,4 --rounds 2 --max-tokens 256 --out results/strata-concurrency.json
"""
import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_models import build_body  # noqa: E402
from openai_probe import stream_chat  # noqa: E402

TOPICS = [
    "how a Kubernetes Deployment rolls out a new ReplicaSet",
    "why ZFS checksums every block and how scrubs use them",
    "how TCP congestion control reacts to packet loss",
    "what a write-ahead log gives a database",
    "how DNS resolution works from a laptop to an authoritative server",
    "why GPUs are fast at matrix multiplication",
    "how a Bloom filter trades memory for false positives",
    "what happens during a TLS 1.3 handshake",
]


def one_round(args, level, rnd):
    results = [None] * level
    start = threading.Barrier(level)

    def worker(i):
        topic = TOPICS[(i + rnd * level) % len(TOPICS)]
        text = (f"[run {uuid.uuid4().hex[:12]}]\nExplain {topic} in about 200 words, in plain prose, "
                "no lists.")
        body = build_body(args.model, text, args.max_tokens, "off", 7 + i)
        start.wait()
        results[i] = stream_chat(args.base_url, body, api_key=args.api_key, timeout=args.timeout)

    t0 = time.monotonic()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(level)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.monotonic() - t0
    comp = sum(((r.get("usage") or {}).get("completion_tokens") or 0) for r in results)
    rows = [{"ttft_s": r["ttft_s"], "decode_tps": r["decode_tps"], "e2e_s": r["e2e_s"], "error": r["error"],
             "completion_tokens": (r.get("usage") or {}).get("completion_tokens")} for r in results]
    return {"level": level, "round": rnd, "wall_s": round(wall, 2), "aggregate_tps": round(comp / wall, 1),
            "requests": rows}


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default="benchmark")
    ap.add_argument("--levels", default="1,2,4")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out")
    args = ap.parse_args()

    rounds = []
    for level in [int(x) for x in args.levels.split(",")]:
        for rnd in range(args.rounds):
            r = one_round(args, level, rnd)
            rounds.append(r)
            errs = [q["error"] for q in r["requests"] if q["error"]]
            print(f"C={level} round={rnd} wall={r['wall_s']}s aggregate={r['aggregate_tps']} tok/s "
                  f"ttft={[q['ttft_s'] for q in r['requests']]} decode={[q['decode_tps'] for q in r['requests']]}"
                  + (f" errors={errs}" if errs else ""), flush=True)

    print("\n| C | aggregate tok/s | per-request decode tok/s | TTFT median | TTFT max | e2e max |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: |")
    summary = []
    for level in sorted({r["level"] for r in rounds}):
        rs = [r for r in rounds if r["level"] == level]
        reqs = [q for r in rs for q in r["requests"]]
        row = {"level": level, "aggregate_tps": med([r["aggregate_tps"] for r in rs]),
               "decode_tps_median": med([q["decode_tps"] for q in reqs]),
               "ttft_median_s": med([q["ttft_s"] for q in reqs]),
               "ttft_max_s": max((q["ttft_s"] or 0) for q in reqs),
               "e2e_max_s": max((q["e2e_s"] or 0) for q in reqs)}
        summary.append(row)
        print(f"| {level} | {row['aggregate_tps']} | {row['decode_tps_median']} | {row['ttft_median_s']} s | "
              f"{row['ttft_max_s']} s | {row['e2e_max_s']} s |")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"model": args.model, "base_url": args.base_url,
                                              "max_tokens": args.max_tokens, "thinking": "off",
                                              "summary": summary, "rounds": rounds}, indent=1))


if __name__ == "__main__":
    main()
