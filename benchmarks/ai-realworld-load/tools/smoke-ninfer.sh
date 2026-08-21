#!/usr/bin/env bash
# NInfer compatibility smoke tests — prove correctness BEFORE benchmarking.
# Each test prints the probe's JSON; judge the content, not just HTTP 200.
#
# Usage:
#   smoke-ninfer.sh all <image-file>
#   smoke-ninfer.sh text|vision|thinking|tools|context [args]
#
# Point at another engine with: BASE_URL=... MODEL=... smoke-ninfer.sh ...
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="${BASE_URL:-https://ninfer.vanillax.me/v1}"
MODEL="${MODEL:-qwen3.8-ninfer}"
PROBE=("$HERE/openai_probe.py" --base-url "$BASE_URL" --model "$MODEL")

t_text() {
  echo "== text: streamed completion (expect ttft_s, decode_tps, usage) =="
  "${PROBE[@]}" --prompt "Explain in exactly three sentences why the sky is blue." --max-tokens 200
}

t_vision() {
  local img="${1:?usage: smoke-ninfer.sh vision <image-file>}"
  echo "== vision: $img — READ the description; it must name details actually present =="
  "${PROBE[@]}" --image "$img" --max-tokens 300 \
    --prompt "Describe this image precisely: name the main objects, any text visible, and the dominant colors."
}

t_thinking() {
  echo "== thinking OFF (server default --no-thinking): reasoning_chars should be 0 =="
  "${PROBE[@]}" --prompt "What is 23*17? Answer with the number only." --max-tokens 64
  echo "== thinking ON (reasoning_effort=medium): reasoning_chars should be > 0 =="
  "${PROBE[@]}" --prompt "What is 23*17? Answer with the number only." --max-tokens 512 \
    --reasoning-effort medium
}

t_tools() {
  echo "== tools: tool_choice=auto — expect a get_weather tool_call with a city argument =="
  echo "   (this is the Perplexica-compatibility gate: no tool_call => NOT Perplexica-ready)"
  "${PROBE[@]}" --tools-demo --max-tokens 256
}

t_context() {
  local tokens="${1:-16000}"
  echo "== context ~${tokens} tokens: needle_found must be true; watch VRAM alongside =="
  echo "   (kubectl -n gpu-operator exec ds/nvidia-powerlimit -- nvidia-smi in another terminal)"
  "${PROBE[@]}" --synthetic-tokens "$tokens" --max-tokens 64
}

case "${1:-all}" in
  text)     t_text ;;
  vision)   shift; t_vision "$@" ;;
  thinking) t_thinking ;;
  tools)    t_tools ;;
  context)  shift; t_context "$@" ;;
  all)      shift || true
            t_text; t_thinking; t_tools
            [ $# -ge 1 ] && t_vision "$1" || echo "== vision: SKIPPED (pass an image file) =="
            t_context 16000 ;;
  *) echo "usage: $0 {all [image]|text|vision <image>|thinking|tools|context [tokens]}"; exit 1 ;;
esac
