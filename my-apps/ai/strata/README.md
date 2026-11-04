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
| Source | `Niko1221/Strata` at the commit pinned in [homelab-images `images/strata`](https://github.com/mitchross/homelab-images/tree/main/images/strata) (v0.1.40.3) |
| Image | `ghcr.io/mitchross/strata:<VERSION>`: CUDA 13.0, sm_86 only, AVX2 CPU build, no vision encoder |
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

## Batch slots and the gateway

`PARALLEL` in the `strata-settings` ConfigMap is Strata's `"parallel"` (upstream
[`docs/BATCHING.md`](https://github.com/Niko1221/Strata/blob/d5ea7133741e67743c0e886bb426c0ce8d69cf6c/docs/BATCHING.md)):
up to N requests decode together, more wait. `prepare.sh` writes it into
`/data/config/strata-iq3_s.json` on every start. It is not part of the settings
stamp, so changing it restarts the pod (experts reload into RAM, a few minutes)
but never reruns setup. `GET /v1/status` -> `concurrency.serving` shows what the
engine actually runs (it drops slots that don't fit in VRAM).

It is **2**: each slot takes ~0.6 GB of the 18.45 GB expert cache (upstream's
formula at 32K resident KV, int8) and ~1.6 GB of pinned RAM (128K streamed KV),
so 2 slots keep the pod near 57 of its 64 GiB limit; 4 would need the limit
raised. Upstream measured a request alone 11 % (2 slots) to 24 % (4 slots)
slower where most experts run on the CPU (12 GB card). On a 4-GPU split two
requests together ran 57 tok/s each (113 total vs 120 alone) and four 205
total. This 2-card split is in between and unmeasured. The slots buy waiting time: with one slot,
measured here, 4 requests at once wait up to 11 s for their first token and 8
up to 23 s ([baseline](../../../benchmarks/ai-realworld-load/baselines/2026-11-03-strata-concurrency-parallel1/results.md)).

LiteLLM's `qwen3.8-27b` (every app's model name) is capped at the same number
with `max_parallel_requests`; one more gets LiteLLM's 429 and falls back to
`deepseek-flash`. `qwen3.8-flash-next` stays local-only and queues here.

## Image updates

The image is built in [mitchross/homelab-images](https://github.com/mitchross/homelab-images/tree/main/images/strata),
not here. Bump `SOURCE_REF` and `VERSION` there, then update both `image:` lines
in `deployment.yaml` to the new `tag@digest` from that run's summary.

## Rollback

Revert the test PR: vLLM gets both cards back, the `qwen3.8-27b` fallback goes
away and Strata is removed (its PV is `Retain`, so the ~92 GB under `strata/`
on the NVMe stays until deleted by hand).
