# vLLM with the qwen3_5 quantized-embedding path wired up (Baseline B, one 3090).
#
# Why this exists (do not replace with a runtime `patch` in the pod):
#   vLLM ships the CompressedTensorsEmbeddingWNA16Int dequant-on-gather kernel,
#   but the qwen3_5 model code never passes quant_config to
#   VocabParallelEmbedding. An INT8 embed_tokens checkpoint therefore fails to
#   load with "no parameter named 'embed_tokens.weight_packed'". Two hunks fix
#   it: the main model and the MTP draft module.
#
# Patch vendored byte-exact from syv-ai/qwen38-27b-rtx3090
#   commit d337c1179b9ba6e4a66e1af2294401ad6e987d06
#   blob   90fca08aa4af71a69ec67f92f714db747160ec28
#
# The RUN below IS the compatibility gate: if a base-image bump moves those
# lines, the build fails here instead of a GPU pod crashlooping at 03:00.
# Revalidate the patch on every vLLM upgrade.
#
# Base is digest-pinned (repo rule: never float on a tag alone) and is the exact
# image Baseline A ran, so quantization is the only engine variable between runs.
FROM vllm/vllm-openai:v0.27.1@sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967

COPY qwen3_5-embed-quant.patch /tmp/qwen3_5-embed-quant.patch
RUN patch -p1 -d /usr/local/lib/python3.12/dist-packages/vllm < /tmp/qwen3_5-embed-quant.patch \
 && rm /tmp/qwen3_5-embed-quant.patch
