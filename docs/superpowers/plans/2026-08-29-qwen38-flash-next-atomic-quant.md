# Qwen3.8 Flash Next Atomic Quant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox notation (`- [ ]`) for tracking.

**Goal:** Replace the active Flash Next GGUF layout with AtomicChat's pinned AD-4.27 Q4 build and prove whether one RTX 3090 can sustain at least 15 generated tokens per second without the current mmap/page-reclaim stall.

**Architecture:** Keep NFS as the durable artifact source and node-local NVMe as the inference source. Stage both the current Unsloth rollback model and AtomicChat's split model, then point llama.cpp at AtomicChat's first ordinary-weight shard while leaving the dedicated N-gram shard mmap-backed on the host. Preserve context, KV, and serving behavior so throughput differences are attributable to artifact layout and expert placement.

**Tech Stack:** Kubernetes, Argo CD sync hooks, Kustomize, llama.cpp CUDA server, Alpine shell, Hugging Face LFS artifacts, MkDocs.

**Spec:** `docs/superpowers/specs/2026-08-29-qwen38-flash-next-atomic-quant-design.md`

## Global Constraints

- Follow root, `my-apps/`, and `my-apps/ai/` `CLAUDE.md` rules.
- Make cluster changes only through Git; do not patch the live Deployment.
- Pin every remote artifact by repository revision, byte size, and LFS SHA-256.
- Do not delete the existing Unsloth model during the trial.
- Keep `--ctx-size 131072`, q8_0/q8_0 KV, one slot, and speculative decoding disabled.
- Never merge the pull request; deployment requires the user to merge.

---

## Task 1: Pin and Download the AtomicChat Q4 Artifact Set

**Files:**

- Modify: `my-apps/ai/llama-cpp/download-model-job.yaml`

- [ ] Query the Hugging Face tree API for revision `142262902a46f7daed19c79d0771534c8106ad59` and capture all 33 files in `Qwen3.8-Flash-Next-AD-4.27bpw-Q4_K_M-M64/` plus `mmproj-Qwen3.8-Flash-Next-F16.gguf`.
- [ ] Verify the inventory has exactly 33 model shards, contiguous indices `00001-of-00033` through `00033-of-00033`, and one projector.
- [ ] Extend the hook so `fetch` accepts a repository URL per artifact family, preserving the existing Unsloth pins and rollback files.
- [ ] Add AtomicChat download calls with exact byte sizes and `.lfs.oid` SHA-256 values into `/models/qwen3.8-flash-next-gguf/atomic-ad-4.27-q4-k-m-m64/` and `/models/qwen3.8-flash-next-gguf/mmproj-F16.gguf`.
- [ ] Run `kustomize build my-apps/ai/llama-cpp --enable-helm` and inspect the rendered download command for all 34 Atomic artifacts.
- [ ] Commit: `feat(ai): pin Atomic Flash Next Q4 artifacts`.

## Task 2: Stage AtomicChat and Rollback Models on Node-Local NVMe

**Files:**

- Modify: `my-apps/ai/llama-cpp/cache-sync-job.yaml`

- [ ] Add the Atomic destination directory without removing `unsloth-ud-q4-k-xl`.
- [ ] Sync all 33 Atomic shards and the F16 projector by name and source size.
- [ ] Preserve the four Unsloth shards and BF16 projector for one-rollout rollback.
- [ ] Ensure partial copies remain atomic via `.part` followed by `mv`, and raise the job deadline enough for the additional approximately 93 GB copy.
- [ ] Render the Kustomization and verify both model families appear in the hook script.
- [ ] Commit: `feat(ai): stage Atomic Flash Next on NVMe`.

## Task 3: Serve the Conservative Atomic Q4 Placement

**Files:**

- Modify: `my-apps/ai/llama-cpp/deployment.yaml`
- Modify: `my-apps/ai/llama-cpp/README.md`
- Modify: `CLAUDE.md`
- Modify: `my-apps/ai/CLAUDE.md`

- [ ] Change `--model` to Atomic shard `00001-of-00033` and `--mmproj` to `mmproj-F16.gguf`.
- [ ] Remove only the `per_layer_token_embd.weight=CPU` override; initially preserve the current CPU expert-layer pattern to isolate the layout change.
- [ ] Keep `--load-mode mmap`, `--tensor-read-lazy auto`, `--fit off`, the 131K context, q8 KV, and all existing API behavior.
- [ ] Update the README with the pinned Atomic profile, the retained Unsloth rollback path, and the explicit warm `tg128 >= 15 tok/s` acceptance gate. Do not claim an unmeasured result.
- [ ] Render the Kustomization and verify the Deployment consumes the Atomic path only after the two wave-0 hooks.
- [ ] Commit: `feat(ai): trial Atomic Flash Next Q4 layout`.

## Task 4: Run Static Repository Validation

**Files:**

- Verify: `my-apps/ai/llama-cpp/*.yaml`
- Verify: `docs/superpowers/specs/2026-08-29-qwen38-flash-next-atomic-quant-design.md`
- Verify: `docs/superpowers/plans/2026-08-29-qwen38-flash-next-atomic-quant.md`

- [ ] Run `kustomize build my-apps/ai/llama-cpp --enable-helm > /tmp/llama-cpp-rendered.yaml`.
- [ ] Run the repository's YAML/Kubernetes schema validation commands used by CI against the rendered output.
- [ ] Run repository policy validation, including the VPA validator if available locally.
- [ ] Run `mkdocs build --strict`; if the tool is unavailable, record that exact limitation and leave the CI check pending rather than installing an unpinned local dependency.
- [ ] Review `git diff --check`, `git diff --stat`, and the full scoped diff for accidental deletions or stale model paths.

## Task 5: Publish the GitOps Trial Without Merging

**Files:**

- Review: all branch changes

- [ ] Push `codex/qwen38-atomic-quant-trial` to origin.
- [ ] Open a pull request that includes the verified failure evidence, artifact/layout change, expected storage impact, acceptance gate, and exact rollback path.
- [ ] Leave the pull request unmerged for the user.

## Task 6: Post-Merge Live Benchmark and Placement Sweep

**Files:**

- Modify after measurement: `my-apps/ai/llama-cpp/deployment.yaml`
- Modify after measurement: `my-apps/ai/llama-cpp/README.md`
- Modify after acceptance: `docs/domains/ai-gpu/3090-llm-optimization.md`
- Modify after acceptance: `docs/domains/ai-gpu/model-catalog.md`

- [ ] Confirm both sync hooks complete, all 34 Atomic files are present on NVMe, and the Deployment reaches Ready with zero restarts/OOM events.
- [ ] Record model load time, CUDA memory, cgroup memory, process read bytes, major faults, CPU utilization, and GPU utilization.
- [ ] Run cold and warm `pp512` and `tg128` tests with the server still configured for 131K context, ensuring the sole slot is otherwise idle.
- [ ] Run one OpenAI-compatible streaming smoke request, one tool-call prompt, and one vision prompt for correctness.
- [ ] If warm `tg128` is below 15 tok/s, move one expert-placement boundary toward GPU residency, repeat the same measurements, and stop before CUDA OOM or unsafe device headroom.
- [ ] If the best safe Atomic Q4 placement remains below 15 tok/s, prepare the separately pinned AD-3.84 IQ4_XS trial described in the design spec; do not combine it with context, KV, or scheduler changes.
- [ ] Once a profile passes, record measured results in the README and AI GPU docs and capture the durable result in Mink.
