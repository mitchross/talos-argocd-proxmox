# Strata — Qwen3.8-Flash-Next on both RTX 3090s (test)

[Strata](https://github.com/Niko1221/Strata) serves Qwen3.8-Flash-Next (a MoE
model): dense layers, KV and a cache of hot experts on the GPUs, all experts in
host RAM. For this test it gets **both** cards and vLLM (`../vllm/`) is parked
at `replicas: 0`; meanwhile LiteLLM sends `qwen3.8-27b` to `deepseek-flash`.

With two cards Strata splits the model by layers ([upstream
`docs/MULTI_GPU.md`](https://github.com/Niko1221/Strata/blob/d5ea7133741e67743c0e886bb426c0ce8d69cf6c/docs/MULTI_GPU.md)):
each card runs a contiguous layer range and caches the experts of its own
layers, so together they hold about twice as many. No NVLink or P2P is needed.
Upstream measured IQ3_S on 2x RTX 3090 + EPYC 7453 (`bench/results/2026-09-29-rtx3090-epyc-milan`,
v0.1.26, 32K prompt): auto split K=24, prompt 749 tok/s, decode 106 tok/s median, needles 3/3.

| Setting | Value |
|---|---|
| Source | `Niko1221/Strata` at `image/SOURCE_REF` (v0.1.40.3), built by `.github/workflows/strata-image.yml` |
| Image | `ghcr.io/mitchross/strata:<image/VERSION>`: CUDA 13.0, sm_86 only, AVX2 CPU build, no vision encoder |
| Model | ISTA-DASLab GSQ-RCO **IQ3_S** GGUF (revision pinned in Strata's `setup.py`) |
| Setup flags | `--family qwen --model IQ3_S --context 131072 --vision no --kv int8 --low-ram off --kv-streaming on --gpus 0,1` |
| API | OpenAI-compatible, `http://strata-service.strata.svc.cluster.local:8080/v1`, no key |
| Gateway | LiteLLM model `qwen3.8-flash-next`; no fallback to or from it |
| GPUs | 2 × RTX 3090 (`nvidia.com/gpu: 2`), layer split `auto` |
| Concurrency | one request at a time; later ones queue |
| Host RAM | 54 GiB request, 64 GiB limit (~47 GiB expert arena) |
| Disk | ~92 GB under `strata/` on the node-local NVMe `/var/mnt/ai-model-cache` |

The settings live in the `strata-settings` ConfigMap (`kustomization.yaml`);
the image's `docker-entrypoint.sh` and `scripts/prepare.sh` read the same
variables.

## First start

1. The `prepare` init container runs Strata's `setup.py --setup --no-start`:
   it downloads the GGUF shards and the MTP layer (~92 GB), builds the pack and
   writes `/data/config/strata-iq3_s.json`. This takes as long as the download.
2. The server container links that config and starts. `/health` answers only
   after the experts are in RAM (a few minutes); the startup probe allows 30.

Later starts skip step 1. Changing a setup value in the ConfigMap restarts the
pod, and `prepare` runs setup again because the saved settings
(`/data/config/strata-iq3_s.json.settings`) no longer match.

The pod uses `gpu-workload-no-preempt`: if the node lacks 54 GiB of
unrequested memory it stays `Pending` instead of evicting other pods. Check
with `kubectl describe node <gpu node>` (Allocated resources, memory).

## Checks

```bash
kubectl -n strata get pods
kubectl -n strata logs deploy/strata-server -c prepare      # first start
kubectl -n strata logs deploy/strata-server
kubectl -n strata port-forward svc/strata-service 18080:8080
curl -fsS http://127.0.0.1:18080/health
curl -fsS http://127.0.0.1:18080/v1/models
```

vLLM is off during the test, so compare against the saved FP8 TP=2 baseline
(`--baseline <results.json>`):
[`benchmarks/ai-realworld-load/tools/README.md`](../../../benchmarks/ai-realworld-load/tools/README.md).

## Image updates

Bump `image/SOURCE_REF` and `image/VERSION` together (VERSION must end in the
first seven characters of the commit), and both `image:` lines in
`deployment.yaml` (then pin `tag@digest` from the run's summary). The workflow refuses mismatches and never overwrites an
existing tag.

## Rollback

Revert the test PR: vLLM gets both cards back, the `qwen3.8-27b` fallback goes
away and Strata is removed (its PV is `Retain`, so the ~92 GB under `strata/`
on the NVMe stays until deleted by hand).
