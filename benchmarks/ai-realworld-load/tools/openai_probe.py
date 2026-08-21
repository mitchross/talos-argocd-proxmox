#!/usr/bin/env python3
"""Backend-neutral OpenAI-compatible streamed probe (stdlib only).

The SAME client code times every engine, so client-side numbers are comparable
by construction:

  ttft_s      first streamed delta (reasoning or content) after request send  MEASURED (client)
  decode_tps  completion_tokens / (last_delta - first_delta)                  DERIVED
  e2e_s       request send -> stream close                                    MEASURED (client)
  usage       engine-reported final-chunk usage (include_usage)               MEASURED (server)

Server-side TTFT/prefill/decode come from each engine's own instrumentation
(vLLM /metrics, NInfer request-log JSONL) and are reported separately — client
and server numbers are never mixed.

Examples:
  openai_probe.py --base-url https://llama.vanillax.me/v1 --model qwen3.8-27b \
      --prompt "say hi in five words"
  openai_probe.py ... --prompt-file w.txt --cold-tag run7 --max-tokens 700
  openai_probe.py ... --image photo.jpg --prompt "Describe every object you see."
  openai_probe.py ... --tools-demo
  openai_probe.py ... --reasoning-effort medium --prompt "23*17?"
  openai_probe.py ... --synthetic-tokens 64000   # context ladder w/ needle recall
"""
import argparse, base64, json, mimetypes, sys, time, urllib.request

NEEDLE = "The maintenance access code for rack seven is JADE-4471."


def synthetic_prompt(n_tokens: int) -> str:
    """Deterministic ~n_tokens filler with a retrieval needle at ~40% depth."""
    para = ("Sensor block %d reported nominal drift within tolerance; the "
            "calibration ledger recorded offset %d micro-units against reference "
            "channel %d, and the supervisor thread rotated its checkpoint without "
            "raising an alert. ")
    parts, i = [], 0
    # ~40 tokens per paragraph at ~4 chars/token
    while sum(len(p) for p in parts) < n_tokens * 4:
        parts.append(para % (i, (i * 37) % 997, i % 16))
        i += 1
    parts.insert(int(len(parts) * 0.4), NEEDLE + " ")
    parts.append("\n\nQuestion: What is the maintenance access code for rack "
                 "seven? Answer with the code only.")
    return "".join(parts)


def data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("--image", help="local image file, sent as a base64 data URI part")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--cold-tag", help="unique first line -> defeats prefix reuse for a cold run")
    ap.add_argument("--reasoning-effort", choices=["none", "low", "medium", "xhigh"])
    ap.add_argument("--tools-demo", action="store_true")
    ap.add_argument("--synthetic-tokens", type=int, help="generate ~N-token needle prompt")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--api-key", default="benchmark")
    args = ap.parse_args()

    if args.synthetic_tokens:
        text = synthetic_prompt(args.synthetic_tokens)
    elif args.prompt_file:
        text = open(args.prompt_file).read()
    elif args.prompt:
        text = args.prompt
    else:
        ap.error("need --prompt, --prompt-file, or --synthetic-tokens")
    if args.cold_tag:
        text = f"[run-id {args.cold_tag} — ignore this line]\n" + text

    content = [{"type": "text", "text": text}]
    if args.image:
        content.insert(0, {"type": "image_url", "image_url": {"url": data_uri(args.image)}})

    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": content if args.image else text}],
        "max_tokens": args.max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if args.reasoning_effort:
        body["reasoning_effort"] = args.reasoning_effort
    if args.tools_demo:
        body["tools"] = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]
        body["tool_choice"] = "auto"
        body["messages"] = [{"role": "user",
                             "content": "What's the weather in Rotterdam right now?"}]

    req = urllib.request.Request(
        args.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {args.api_key}"},
    )

    out = {"base_url": args.base_url, "model": args.model, "status": None,
           "ttft_s": None, "decode_tps": None, "e2e_s": None, "usage": None,
           "finish_reason": None, "tool_calls": [], "reasoning_chars": 0,
           "content_chars": 0, "text_head": "", "needle_found": None, "error": None}

    t0 = time.monotonic()
    t_first = t_last = None
    text_out, reasoning_len = [], 0
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            out["status"] = resp.status
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if obj.get("usage") and not obj.get("choices"):
                    out["usage"] = obj["usage"]
                    continue
                for ch in obj.get("choices", []):
                    d = ch.get("delta", {})
                    got = False
                    if d.get("reasoning_content"):
                        reasoning_len += len(d["reasoning_content"]); got = True
                    if d.get("content"):
                        text_out.append(d["content"]); got = True
                    if d.get("tool_calls"):
                        out["tool_calls"].append(d["tool_calls"]); got = True
                    if got:
                        now = time.monotonic()
                        if t_first is None:
                            t_first = now
                        t_last = now
                    if ch.get("finish_reason"):
                        out["finish_reason"] = ch["finish_reason"]
                    # some engines put usage on the last choices chunk
                    if obj.get("usage"):
                        out["usage"] = obj["usage"]
    except Exception as e:  # noqa: BLE001 — report, don't crash the harness
        out["error"] = f"{type(e).__name__}: {e}"

    t_end = time.monotonic()
    full = "".join(text_out)
    out["e2e_s"] = round(t_end - t0, 3)
    out["ttft_s"] = round(t_first - t0, 3) if t_first else None
    out["reasoning_chars"] = reasoning_len
    out["content_chars"] = len(full)
    out["text_head"] = full[:200]
    comp = (out["usage"] or {}).get("completion_tokens")
    if comp and t_first and t_last and t_last > t_first:
        out["decode_tps"] = round(comp / (t_last - t_first), 2)
    if args.synthetic_tokens:
        out["needle_found"] = "JADE-4471" in full
    print(json.dumps(out, indent=2))
    sys.exit(0 if not out["error"] else 1)


if __name__ == "__main__":
    main()
