#!/usr/bin/env bash
# First controlled A/B: ~6K-token fixed prompt (workloads/ab-6k-prompt.txt,
# 6,055 tokens by the live Qwen tokenizer), ~550-600 generated tokens, C1,
# one GPU per engine, vision LOADED on both servers (request itself is text).
#
# Per engine, two passes with the byte-identical prompt:
#   cold  — unique run-id first line => prefix reuse CANNOT hit
#   warm  — the cold prompt repeated verbatim => prefix reuse SHOULD hit
#
# Client-side numbers (ttft/decode_tps/e2e) come from the same probe code for
# both engines. Engine-side numbers come from each engine's own run collector
# (collect.sh for vLLM, collect-ninfer.sh for NInfer) started around this script.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PROMPT="$ROOT/workloads/ab-6k-prompt.txt"
MAX_TOKENS=700

CONTROL_URL="${CONTROL_URL:-https://vllm.vanillax.me/v1}"
CONTROL_MODEL="${CONTROL_MODEL:-qwen3.8-27b}"
CANDIDATE_URL="${CANDIDATE_URL:-https://ninfer.vanillax.me/v1}"
CANDIDATE_MODEL="${CANDIDATE_MODEL:-qwen3.8-ninfer}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/runs/${TS}_ab-smallload"
mkdir -p "$OUT"
TAG="ab-$TS"

run_pair() { # engine base_url model
  local engine="$1" url="$2" model="$3"
  echo "--- $engine cold (prefix-defeating tag) ---"
  python3 "$HERE/openai_probe.py" --base-url "$url" --model "$model" \
    --prompt-file "$PROMPT" --cold-tag "$TAG-$engine" --max-tokens $MAX_TOKENS \
    > "$OUT/${engine}-cold.json" || true
  echo "--- $engine warm (identical prompt repeated) ---"
  python3 "$HERE/openai_probe.py" --base-url "$url" --model "$model" \
    --prompt-file "$PROMPT" --cold-tag "$TAG-$engine" --max-tokens $MAX_TOKENS \
    > "$OUT/${engine}-warm.json" || true
}

run_pair control   "$CONTROL_URL"   "$CONTROL_MODEL"
run_pair candidate "$CANDIDATE_URL" "$CANDIDATE_MODEL"

echo
printf "%-18s %8s %8s %10s %10s %8s %8s\n" run prompt compl ttft_s decode_tps e2e_s status
for f in control-cold control-warm candidate-cold candidate-warm; do
  python3 - "$OUT/$f.json" "$f" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1])); u = d.get("usage") or {}
print(f"{sys.argv[2]:<18} {u.get('prompt_tokens','-'):>8} {u.get('completion_tokens','-'):>8} "
      f"{d.get('ttft_s','-'):>10} {d.get('decode_tps','-'):>10} {d.get('e2e_s','-'):>8} "
      f"{d.get('error') or d.get('status'):>8}")
EOF
done
echo
echo "RUN=$OUT   (client-side numbers; pair with each engine's collector for server-side)"
