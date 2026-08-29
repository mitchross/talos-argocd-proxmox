# Qwen3.8 Flash Next Atomic Quant Trial Design

**Status:** Approved for implementation

## Purpose

Make Qwen3.8 Flash Next usable as the cluster's primary local model on one RTX
3090 and a 100 GiB Threadripper 2950X worker. The first performance target is
at least 15 generated tokens per second without the page-cache stalls observed
with the current Unsloth UD-Q4_K_XL deployment.

This is a controlled model-layout trial, not a claim that a 24 GiB card can
match the 36 tok/s unified-memory or four-GPU results published elsewhere.

## Current State and Verified Failure

The live server runs llama.cpp b10666 with the 111 GB Unsloth UD-Q4_K_XL
family, a BF16 projector, 131,072-token q8_0/q8_0 KV, lazy PLE reads, and expert
tensors from blocks 9-46 on CPU. Only about ten layers' expert tensors remain
on the GPU.

The 2026-08-29 live evidence showed:

- 310 prompt tokens at 3.49 tok/s and 86 generated tokens at 0.17 tok/s;
- a subsequent request stalled at 374 of 376 prompt tokens while the GPU was
  idle;
- zero container restarts and zero cgroup OOM events;
- approximately 131 GB of process reads, 10.8 million file-cache refaults, and
  sustained full memory pressure around 44-50%;
- ordinary workloads sharing the untainted GPU worker and competing for CPU
  and memory bandwidth.

The model is therefore not failing because its context window or KV cache is
intrinsically too large. Its ordinary weights and PLE table leave too little
headroom under the current shard layout, and the CPU-offloaded expert path is
competing with host page reclaim and unrelated pods.

## Decision

Trial AtomicChat's `AD-4.27bpw-Q4_K_M-M64` GGUF first. AtomicChat publishes it
as 92.9 GB total, with 54.5 GB of ordinary weights in fast memory and a 38.4 GB
N-gram-only shard left on SSD. Its published quality measurements are 0.0842 KL
divergence and 89.49% top-1 agreement against BF16. This is the highest-quality
Atomic build whose stated resident set comfortably fits the worker's combined
RAM and VRAM with 131K context headroom.

The model remains on the existing node-local NVMe cache. llama.cpp keeps mmap
enabled so the N-gram-only shard is pageable. The explicit
`per_layer_token_embd` override is removed because the table is model-level,
host-side by default, and physically isolated from ordinary weights in this
build.

Expert placement is discovered empirically rather than frozen to the current
block pattern. Start conservatively, then move expert layers onto the GPU until
the loaded process leaves safe CUDA headroom for the 131K symmetric KV cache
and compute buffers. Change only one placement boundary per benchmark round.

If the Q4 build cannot reach 15 tok/s after placement is maximized, trial
AtomicChat's `AD-3.84bpw-IQ4_XS-M64`. It reduces the stated resident weights to
45.8 GB and should permit more GPU-resident expert layers, at the accepted cost
of lower published fidelity: 0.2277 KL divergence and 82.68% top-1 agreement.

## Runtime Profile

The first trial retains the product behavior users already depend on:

- one OpenAI-compatible server slot;
- 131,072-token context allocation;
- symmetric q8_0 K/V cache and Flash Attention;
- vision through AtomicChat's shared F16 projector;
- Jinja chat templating and the existing reasoning defaults;
- node-local NVMe as the inference source and NFS as the retained source copy.

`--load-mode none` is not part of the initial Atomic trial. AtomicChat's layout
and guide explicitly use mmap to page the separate N-gram shard. A later
llama.cpp build may adopt the open loader and batched-readahead work after it is
merged or after a separately reviewed custom-image decision; the first trial
does not combine an unmerged runtime patch with a new quant.

MTP and N-gram speculative decoding remain disabled during the baseline. They
change generation mechanics and would make it impossible to attribute a speed
change to model residency and placement.

## Controlled Rollout

### Phase 1: stage without serving

Pin the AtomicChat repository revision and every shard digest in the download
hook. Retain the existing Unsloth files on NFS and node-local NVMe so rollback
does not require another 100 GB transfer. Update the cache-sync hook to stage
the Atomic Q4 shards and F16 projector without deleting either model family.

Expected result: every pinned file exists on NFS and local NVMe with the exact
declared byte size and SHA-256 digest. Stop if AtomicChat changes the published
file set, a digest differs, or local NVMe cannot hold both model families.

### Phase 2: serve a conservative placement

Change only the Deployment's model path, projector path, PLE override, and
initial expert placement. Preserve the current context, KV, batch, sampling,
and API settings. Argo CD performs the normal `Recreate` rollout.

Expected result: the pod reaches Ready with one 131,072-token slot, zero
restarts, no OOM event, and several GiB of host and device headroom. Stop before
benchmarking if the loader wires the N-gram shard into CUDA memory, ordinary
weights continually refault from disk, or available host memory falls below
the amount needed by system workloads.

### Phase 3: tune one placement boundary at a time

Run the same cold and warm benchmark at each expert-placement boundary. Move
the boundary only after recording model load time, prompt throughput,
generation throughput, GPU memory, host memory, major faults, process read
bytes, CPU utilization, and GPU utilization.

The primary acceptance test is a warm single-stream `tg128` result of at least
15 tok/s with the server configured for 131K context. Also run `pp512` and an
OpenAI-compatible streaming request to verify TTFT and real server behavior.
Depth runs at 8K, 32K, and 100K record the expected long-context degradation;
they do not replace the primary short-depth target.

### Phase 4: choose quality or speed tier

Keep `AD-4.27bpw-Q4_K_M-M64` if it meets the target. If its best safe placement
is below 15 tok/s, repeat phases 1-3 with `AD-3.84bpw-IQ4_XS-M64`. Do not change
context size, KV type, speculative decoding, or CPU scheduling in the same
comparison.

### Phase 5: isolate host resources if still required

If the selected Atomic build meets the target only when unrelated pods are
quiet, make GPU-worker isolation a separate GitOps change. Taint the worker
through its owning Talos/Omni configuration and verify required DaemonSets
tolerate the taint before eviction. Ordinary workloads such as Loki and
PostHog must move elsewhere; hardware, networking, storage, and observability
DaemonSets remain.

This phase is separate because changing the quant and scheduler population at
once would hide which intervention fixed the stall.

## Files and Sources of Truth

The implementation owns:

- `my-apps/ai/llama-cpp/download-model-job.yaml` for pinned source artifacts;
- `my-apps/ai/llama-cpp/cache-sync-job.yaml` for node-local staging;
- `my-apps/ai/llama-cpp/deployment.yaml` for model and runtime placement;
- `my-apps/ai/llama-cpp/README.md` for measured results and rollback;
- `docs/domains/ai-gpu/3090-llm-optimization.md` and
  `docs/domains/ai-gpu/model-catalog.md` for the accepted production profile.

External evidence:

- AtomicChat guide and published residency/quality figures:
  <https://atomic.chat/blog/guides/how-to-run-qwen-3-8-flash-next-locally>
- AtomicChat model repository:
  <https://huggingface.co/AtomicChat/Qwen3.8-Flash-Next-GGUF>
- llama.cpp lazy tensor loader PR:
  <https://github.com/ggml-org/llama.cpp/pull/27794>
- pending loader interaction fix:
  <https://github.com/ggml-org/llama.cpp/pull/27837>
- pending batched PLE readahead measurements:
  <https://github.com/unslothai/llama.cpp/pull/137>

## Validation

Static validation must render the Kustomization, validate YAML, run repository
policy checks, and build documentation strictly. Artifact validation must
compare every downloaded file to its pinned byte size and digest before the
Deployment can consume it.

Live validation must record both cold and warm timings. A result is not valid
if another request occupied the sole slot, the pod restarted, the prompt cache
changed between comparison arms, or the GPU worker's competing workload
changed materially during the run.

Output correctness remains a gate: deterministic smoke prompts, one tool call,
and one vision prompt must remain coherent before throughput is accepted.

## Rollback

Rollback changes the Deployment path and placement flags back to the retained
Unsloth UD-Q4_K_XL files. No model is deleted during the trial, so rollback is
one normal Argo CD `Recreate` rollout and requires no download.

If the Atomic download or local-cache sync fails, stop before changing the
Deployment. If the Atomic pod loads but stalls, OOMs, or emits incoherent
output, revert the serving commit; do not add simultaneous speculative,
context, or KV changes in an attempt to rescue that run.

Model cleanup is a later, explicit storage decision after the selected profile
has remained stable. It is not part of this trial.
