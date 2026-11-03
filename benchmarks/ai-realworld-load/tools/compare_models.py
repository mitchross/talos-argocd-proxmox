#!/usr/bin/env python3
"""Send one fixed prompt set to several LiteLLM models and save the results side by side (stdlib only).

Every request goes through openai_probe.stream_chat, so both models are timed by the same client code:

  ttft_s       request send -> first streamed reasoning/answer delta        MEASURED (client)
  prefill_tps  prompt_tokens / ttft_s                                      DERIVED (includes queue + gateway)
  decode_tps   completion_tokens / (last delta - first delta)              DERIVED
  total_s      request send -> stream close                                MEASURED (client)
  tokens       the engine's own usage block                                MEASURED (server)

Each request gets a unique first line, so neither engine's prefix cache can serve it.
Strata serves one request at a time: run this when nothing else uses the models.

Examples:
  LITELLM_API_KEY=... compare_models.py --base-url https://litellm.vanillax.me/v1
  compare_models.py --models qwen3.8-27b,qwen3.8-flash-next --repeats 3 --thinking medium
  compare_models.py --models qwen3.8-27b --only short-chat        # quick check of one model
"""
import argparse, html, json, os, statistics, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openai_probe import NEEDLE, stream_chat, synthetic_prompt  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_PROMPTS = HERE.parent / "workloads" / "compare-prompts.json"
DEFAULT_MODELS = "qwen3.8-27b,qwen3.8-flash-next"
# Qwen's published samplers (my-apps/ai/vllm/README.md); the same values go to every model.
SAMPLERS = {
    "off": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
            "presence_penalty": 1.5, "repetition_penalty": 1.0},
    "on": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
           "presence_penalty": 0.0, "repetition_penalty": 1.05},
}


def build_body(model, text, max_tokens, thinking, seed):
    if thinking == "off":
        kwargs = {"enable_thinking": False, "preserve_thinking": False}
        sampler = SAMPLERS["off"]
    else:
        kwargs = {"enable_thinking": True, "reasoning_effort": thinking}
        sampler = SAMPLERS["on"]
    extra = {"chat_template_kwargs": kwargs, **{k: sampler[k] for k in ("top_k", "min_p", "repetition_penalty")}}
    # Same fields top-level and in extra_body, like the Open WebUI Qwen filter, so LiteLLM forwards them.
    return {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
            "stream": True, "stream_options": {"include_usage": True}, "seed": seed,
            **sampler, **extra, "extra_body": extra}


def prompt_text(spec):
    if spec.get("synthetic_tokens"):
        return synthetic_prompt(spec["synthetic_tokens"])
    return spec["prompt"]


def run_one(args, run_id, spec, model, repeat):
    tag = f"[run-id {run_id}-{model}-{spec['id']}-{repeat} — ignore this line]\n"
    body = build_body(model, tag + prompt_text(spec), spec["max_tokens"], args.thinking, args.seed)
    r = stream_chat(args.base_url, body, args.api_key, args.timeout)
    usage = r.get("usage") or {}
    pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
    row = {"prompt_id": spec["id"], "model": model, "repeat": repeat, "status": r["status"],
           "error": r["error"], "finish_reason": r["finish_reason"], "prompt_tokens": pt,
           "completion_tokens": ct, "ttft_s": r["ttft_s"], "decode_tps": r["decode_tps"],
           "total_s": r["e2e_s"],
           "prefill_tps": round(pt / r["ttft_s"], 1) if pt and r["ttft_s"] else None,
           "content": r["content"], "reasoning": r["reasoning"]}
    if spec.get("expect"):
        row["expect_found"] = spec["expect"] in r["content"]
    return row


def median(rows, key):
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return round(statistics.median(vals), 2) if vals else None


def summarize(results, prompts, models):
    table = []
    for spec in prompts:
        for model in models:
            rows = [r for r in results if r["prompt_id"] == spec["id"] and r["model"] == model]
            ok = [r for r in rows if not r["error"]]
            table.append({"prompt_id": spec["id"], "model": model, "runs": len(rows), "errors": len(rows) - len(ok),
                          **{k: median(ok, k) for k in ("ttft_s", "prefill_tps", "decode_tps", "total_s",
                                                         "prompt_tokens", "completion_tokens")},
                          "finish": ",".join(sorted({str(r["finish_reason"]) for r in ok})) or "-",
                          "expect_found": (all(r.get("expect_found") for r in ok) if ok and "expect" in spec
                                           else None)})
    return table


def cell(v):
    return "-" if v is None else str(v)


def markdown(meta, table, results, prompts, models):
    out = [f"# LLM comparison {meta['run_id']}", "",
           f"Gateway `{meta['base_url']}` · thinking `{meta['thinking']}` · repeats {meta['repeats']} · "
           f"started {meta['started']}", "",
           "Client-side timings through LiteLLM; medians over repeats. prefill tok/s = prompt tokens / TTFT.", "",
           "| Prompt | Model | TTFT s | Prefill tok/s | Decode tok/s | Total s | Prompt tok | Output tok | "
           "Finish | Errors |", "|---|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for t in table:
        finish = t["finish"] + ("" if t["expect_found"] is None else
                                (" ✓needle" if t["expect_found"] else " ✗needle"))
        out.append(f"| {t['prompt_id']} | {t['model']} | {cell(t['ttft_s'])} | {cell(t['prefill_tps'])} | "
                   f"{cell(t['decode_tps'])} | {cell(t['total_s'])} | {cell(t['prompt_tokens'])} | "
                   f"{cell(t['completion_tokens'])} | {finish} | {t['errors']} |")
    out += ["", "## Outputs (first repeat)", ""]
    for spec in prompts:
        out += [f"### {spec['title']} (`{spec['id']}`)", "", "<table><tr>" +
                "".join(f"<th>{html.escape(m)}</th>" for m in models) + "</tr><tr>"]
        for model in models:
            row = next((r for r in results if r["prompt_id"] == spec["id"] and r["model"] == model
                        and r["repeat"] == 0), None)
            text = "(missing)" if row is None else (row["error"] or row["content"])
            out.append(f'<td valign="top"><pre>{html.escape(text)}</pre></td>')
        out += ["</tr></table>", ""]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=os.environ.get("LITELLM_BASE_URL", "https://litellm.vanillax.me/v1"))
    ap.add_argument("--api-key", default=os.environ.get("LITELLM_API_KEY") or os.environ.get("LITELLM_MASTER_KEY"))
    ap.add_argument("--models", default=DEFAULT_MODELS, help="comma-separated LiteLLM model names")
    ap.add_argument("--prompts", default=str(DEFAULT_PROMPTS))
    ap.add_argument("--only", help="comma-separated prompt ids to run (default: all)")
    ap.add_argument("--thinking", default="off", choices=["off", "low", "medium", "xhigh"])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--no-warmup", action="store_true", help="skip the untimed one-line request per model")
    ap.add_argument("--out", help="output folder (default: runs/<UTC time>_compare next to tools/)")
    ap.add_argument("--print", action="store_true", help="also print results.md and results.json to stdout")
    args = ap.parse_args()
    if not args.api_key:
        ap.error("set LITELLM_API_KEY (or pass --api-key)")

    prompts = json.loads(Path(args.prompts).read_text())["prompts"]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = wanted - {p["id"] for p in prompts}
        if unknown:
            ap.error(f"unknown prompt id(s): {', '.join(sorted(unknown))}")
        prompts = [p for p in prompts if p["id"] in wanted]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(args.out or HERE.parent / "runs" / f"{run_id}_compare")
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"run_id": run_id, "base_url": args.base_url, "models": models, "thinking": args.thinking,
            "repeats": args.repeats, "seed": args.seed, "started": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
            "prompts_file": Path(args.prompts).name, "prompt_ids": [p["id"] for p in prompts], "needle": NEEDLE}

    if not args.no_warmup:
        for model in models:
            w = stream_chat(args.base_url, build_body(model, f"[warmup {run_id}] Say OK.", 8, "off", args.seed),
                            args.api_key, args.timeout)
            print(f"warmup {model}: status={w['status']} error={w['error']}", file=sys.stderr, flush=True)

    results = []
    for repeat in range(args.repeats):
        for spec in prompts:
            for model in models:       # alternate models per prompt so slow drift hits both alike
                row = run_one(args, run_id, spec, model, repeat)
                results.append(row)
                print(f"{spec['id']:<20} {model:<22} ttft={row['ttft_s']} decode={row['decode_tps']} "
                      f"total={row['total_s']} err={row['error']}", file=sys.stderr, flush=True)
                (out_dir / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))

    table = summarize(results, prompts, models)
    doc = {"meta": meta, "summary": table,
           "side_by_side": {spec["id"]: {r["model"]: r for r in results if r["prompt_id"] == spec["id"]
                                         and r["repeat"] == 0} for spec in prompts},
           "results": results}
    (out_dir / "results.json").write_text(json.dumps(doc, indent=2))
    md = markdown(meta, table, results, prompts, models)
    (out_dir / "results.md").write_text(md)
    print(f"wrote {out_dir}/results.json and results.md", file=sys.stderr)
    if args.print:
        print("=== results.md ===\n" + md + "=== end results.md ===")
        print("=== results.json ===\n" + json.dumps(doc) + "\n=== end results.json ===")
    sys.exit(1 if any(r["error"] for r in results) else 0)


if __name__ == "__main__":
    main()
