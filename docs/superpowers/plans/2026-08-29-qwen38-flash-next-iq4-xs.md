# Qwen3.8 Flash Next IQ4_XS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the active AtomicChat auto-fit profile with Unsloth UD-IQ4_XS and explicit expert-only CPU placement, using the existing prebuilt llama.cpp image, then publish the GitOps change as an unmerged pull request.

**Architecture:** Keep the existing NFS-to-node-local-NVMe artifact flow and immutable official llama.cpp image. Add the pinned three-shard IQ4_XS model, hydrate it before Deployment wave 1, and run all non-expert layer work on CUDA while keeping the first 45 MoE expert blocks in host RAM. Preserve the API alias, 131K context, q8/q8 KV, and rollback assets so throughput is the only intended behavioral change.

**Tech Stack:** Kubernetes, Argo CD sync hooks, Kustomize, llama.cpp CUDA server, Alpine shell, Hugging Face LFS, GitHub pull requests.

**Spec:** `docs/superpowers/specs/2026-08-29-qwen38-flash-next-iq4-xs-design.md`

## Global Constraints

- Follow root, `my-apps/`, and `my-apps/ai/` `CLAUDE.md` rules.
- Make cluster changes only through Git; do not patch the live Deployment.
- Retain official image build `10666` at digest `sha256:a2d04d1d1c2b2abe287fef9a22a3700a7fa20aec4c4ab56135e0099f38119848`.
- Pin Unsloth revision `c8b5954a88c2775c546b92593eda40ea041d3176`, byte sizes, and SHA-256 values exactly as specified.
- Keep `--ctx-size 131072`, q8_0/q8_0 KV, one slot, and speculative decoding disabled.
- Retain AtomicChat and UD-Q4_K_XL files for rollback.
- Never merge the pull request; deployment requires the user to merge.

---

### Task 1: Add the Pinned IQ4_XS Artifact Set

**Files:**
- Modify: `my-apps/ai/llama-cpp/download-model-job.yaml`

**Interfaces:**
- Consumes: existing `fetch REPO NAME DEST SIZE SHA256` shell function and pinned Unsloth repository URL.
- Produces: verified NFS files under `qwen3.8-flash-next-gguf/unsloth-ud-iq4-xs/` for the cache hydration hook.

- [ ] **Step 1: Write a failing artifact-inventory assertion**

  Run a shell assertion requiring the three IQ4_XS shard names and their expected sizes/checksums in `download-model-job.yaml`; expect failure because the directory and calls do not exist yet.

- [ ] **Step 2: Add IQ4_XS downloads**

  Extend the existing `mkdir -p` list with `"$BASE/unsloth-ud-iq4-xs"`. Add three `fetch` calls for `UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf` through `00003-of-00003.gguf`, targeting the new directory with the exact values from the spec. Reuse the already-pinned BF16 projector.

- [ ] **Step 3: Run the artifact assertion and render test**

  Run the inventory assertion again and `kustomize build my-apps/ai/llama-cpp --enable-helm`; expect all three shards exactly once and a successful render.

- [ ] **Step 4: Commit the model acquisition change**

  Stage only `download-model-job.yaml` and commit `feat(ai): pin Flash Next IQ4_XS artifacts`.

### Task 2: Hydrate IQ4_XS to Node-Local NVMe

**Files:**
- Modify: `my-apps/ai/llama-cpp/cache-sync-job.yaml`

**Interfaces:**
- Consumes: the three verified NFS files produced by Task 1.
- Produces: size-checked, atomically copied NVMe files under `unsloth-ud-iq4-xs/` before Deployment wave 1.

- [ ] **Step 1: Write a failing cache inventory assertion**

  Require the new directory and a loop that resolves all three `0000N-of-00003` shard paths; expect failure before editing.

- [ ] **Step 2: Add the cache directory and sync loop**

  Add `"$DST/unsloth-ud-iq4-xs"` to `mkdir -p`, then call `sync_one` for shards 1 through 3. Preserve AtomicChat, UD-Q4_K_XL, and both projectors.

- [ ] **Step 3: Run the cache assertion and render test**

  Confirm the three-shard loop is present, the `.part` plus atomic `mv` behavior is unchanged, and Kustomize renders successfully.

- [ ] **Step 4: Commit the NVMe hydration change**

  Stage only `cache-sync-job.yaml` and commit `feat(ai): stage Flash Next IQ4_XS on NVMe`.

### Task 3: Switch to Expert-Only CPU Placement

**Files:**
- Modify: `my-apps/ai/llama-cpp/deployment.yaml`

**Interfaces:**
- Consumes: the IQ4_XS entry shard and existing BF16 projector from node-local NVMe.
- Produces: the unchanged OpenAI-compatible endpoint and alias with explicit CUDA/non-expert and CPU/expert placement.

- [ ] **Step 1: Write failing runtime-profile assertions**

  Assert the Deployment contains the IQ4_XS entry shard, `--n-gpu-layers 99`, `--fit off`, `--n-cpu-moe 45`, `--ubatch-size 2048`, mmap, lazy reads `on`, BF16 projector, and no `--no-mmproj-offload`; expect failure against auto-fit.

- [ ] **Step 2: Apply the minimal runtime profile**

  Switch the model path to `unsloth-ud-iq4-xs/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf` and projector to `mmproj-BF16.gguf`. Remove `--no-mmproj-offload`, `--fit-ctx`, and `--fit-target`; set `--fit off`, `--n-gpu-layers 99`, `--n-cpu-moe 45`, `--ubatch-size 2048`, and `--tensor-read-lazy on`. Preserve context, q8/q8 KV, alias, reasoning, sampling, probes, and resources.

- [ ] **Step 3: Run runtime assertions and render test**

  Confirm each required flag appears exactly once, removed auto-fit flags are absent, and Kustomize renders successfully.

- [ ] **Step 4: Commit the runtime change**

  Stage only `deployment.yaml` and commit `feat(ai): use IQ4_XS expert-only offload`.

### Task 4: Update Current-State Documentation

**Files:**
- Modify: `my-apps/ai/llama-cpp/README.md`
- Modify: `CLAUDE.md`
- Modify: `my-apps/ai/CLAUDE.md`
- Modify: `docs/domains/ai-gpu/model-catalog.md`

**Interfaces:**
- Consumes: the exact runtime and artifact pins from Tasks 1-3.
- Produces: current-state operational guidance, performance gate, and rollback instructions for maintainers.

- [ ] **Step 1: Replace obsolete active-profile claims**

  Document Unsloth UD-IQ4_XS, BF16 vision on CUDA, explicit 45-block expert CPU placement, mmap/lazy n-grams, q8/q8 KV, and the retained official prebuilt image. Remove claims that AtomicChat auto-fit is the active profile.

- [ ] **Step 2: Preserve measured results as historical evidence**

  Keep the prior Atomic/auto-fit throughput numbers clearly labeled as historical. State `warm tg128 >= 15 tok/s` as pending acceptance rather than claiming success.

- [ ] **Step 3: Document exact rollback**

  Record the prior AtomicChat model path, F16 projector, auto-fit arguments, and unchanged image digest as the one-commit rollback profile.

- [ ] **Step 4: Validate documentation consistency**

  Search the changed current-state sections for stale `AtomicChat AD-4.27` active claims and confirm the API alias remains `Qwen3.8-Flash-Next Q4` everywhere it is documented.

- [ ] **Step 5: Commit documentation**

  Stage only the four documentation files and commit `docs(ai): document IQ4_XS placement trial`.

### Task 5: Run Static Verification

**Files:**
- Verify: `my-apps/ai/llama-cpp/*.yaml`
- Verify: `docs/superpowers/specs/2026-08-29-qwen38-flash-next-iq4-xs-design.md`
- Verify: `docs/superpowers/plans/2026-08-29-qwen38-flash-next-iq4-xs.md`

**Interfaces:**
- Consumes: the complete branch diff.
- Produces: reproducible evidence that the GitOps application renders and repository policies pass before publication.

- [ ] **Step 1: Render the application**

  Run `kustomize build my-apps/ai/llama-cpp --enable-helm > /tmp/llama-cpp-iq4-xs.yaml`; expect exit 0 and a non-empty multi-document manifest.

- [ ] **Step 2: Validate placement and wave invariants in the render**

  Assert download wave `-1`, cache wave `0`, Deployment wave `1`, IQ4_XS model path, expert-only flags, 131072 context, q8/q8 KV, and the immutable image digest.

- [ ] **Step 3: Run repository policy checks**

  Generate the all-app manifest stream using the same loop as `.github/workflows/cluster-ci.yml`, then run `python3 scripts/validate-kopiur-coverage.py` and `python3 scripts/validate-vpa-policies.py` against it.

- [ ] **Step 4: Run documentation and diff checks**

  Run `mkdocs build --strict` if installed, `git diff --check`, inspect `git diff --stat`, and review the full branch diff against `origin/main`.

### Task 6: Publish an Unmerged Draft Pull Request

**Files:**
- Review: all branch commits and changes.

**Interfaces:**
- Consumes: the verified feature branch.
- Produces: a pushed branch and draft GitHub pull request targeting `main`; the user remains the only merge actor.

- [ ] **Step 1: Confirm the planning commits are present**

  Confirm the design spec and implementation plan commits precede the implementation commits in the branch history.

- [ ] **Step 2: Push the feature branch**

  Push `feat/llama-beellama-iq4-xs` to `origin` without force.

- [ ] **Step 3: Open the draft pull request**

  Create one draft PR from `feat/llama-beellama-iq4-xs` to `main`. Include the measured 0.44-0.58 tok/s auto-fit failure, prebuilt-image decision, exact IQ4_XS placement, 15 tok/s acceptance gate, storage impact, validation commands, and rollback profile.

- [ ] **Step 4: Leave the PR unmerged**

  Report the PR URL and pending post-merge ArgoCD/live benchmark steps. Do not merge even if CI passes.
