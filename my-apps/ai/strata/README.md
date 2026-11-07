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
| Source | `Niko1221/Strata` at the commit pinned in [homelab-images `images/strata`](https://github.com/mitchross/homelab-images/tree/main/images/strata) (v0.2.11, engine 0.1.57) |
| Image | `ghcr.io/mitchross/strata:<VERSION>`: CUDA 13.0, sm_86 only, AVX2 CPU build, CUDA image encoder (`strata-vision`) |
| Model | ISTA-DASLab GSQ-RCO **IQ3_S** GGUF (revision pinned in Strata's `setup.py`) |
| Launch settings | `FAMILY=qwen MODEL=IQ3_S CONTEXT=131072 VISION=yes KV=int8 GPUS=0,1 PARALLEL=1 API_KEY=none` |
| API | OpenAI-compatible, `http://strata-service.strata.svc.cluster.local:8080/v1`, no key (`API_KEY=none`) |
| Gateway | LiteLLM model `qwen3.8-flash-next`; no fallback to or from it |
| GPUs | 2 × RTX 3090 (`nvidia.com/gpu: 2`), layer split `auto` |
| Concurrency | one request at a time; later ones queue |
| Host RAM | 54 GiB request, 64 GiB limit (~47 GiB expert arena) |
| Disk | ~92 GB under `strata/Strata-data/` on the node-local NVMe `/var/mnt/ai-model-cache` |

The settings live in the `strata-settings` ConfigMap (`kustomization.yaml`).
The image's entrypoint (upstream [`docker/entrypoint.sh`](https://github.com/Niko1221/Strata/blob/v0.2.11/docker/entrypoint.sh),
[`docs/DOCKER.md`](https://github.com/Niko1221/Strata/blob/v0.2.11/docs/DOCKER.md)) turns them into
`strata launch --no-tui` flags and saves them as the `docker` preset in `/data/state`.

## First start

1. `keep-old-paths` moves 0.1.x's `/data/models`, `/data/packs` and `/data/mtp`
   into `/data/Strata-data` (a rename, nothing is copied) and leaves links at
   the old places, so a revert to 0.1.x still finds its files.
2. The server container runs `strata launch`: setup checks or downloads the
   GGUF shards, MTP layer and mmproj (~92 GB on an empty volume), builds the
   pack and writes run settings under `/data/install`, then loads and serves.
   `/health` answers only after the experts are in RAM; the startup probe
   allows 60 minutes.

Later starts reuse what is there. Changing a setting in the ConfigMap restarts
the pod, and setup redoes only the steps that setting changes.

The pod uses `gpu-workload-high`: if the node lacks 54 GiB of unrequested
memory, it evicts ordinary pods (priority below 1000) and they restart on other
nodes. Pods with a higher class, such as `app-critical`, stay put. Check with
`kubectl describe node <gpu node>` (Allocated resources, memory).

## Images (vision)

`VISION=yes` runs Strata's image encoder on the GPU, so `qwen3.8-flash-next`
reads screenshots and photos itself. It needs an image built with
`BUILD_VISION=1` (`0.1.40.3.1` and later). Without the encoder Strata answers
an image with `400 ... started without the vision encoder`.

- Setup downloads `mmproj-Qwen3.8-Flash-Next-BF16.gguf` (~0.9 GB) from the
  same pinned ISTA revision as the GGUFs. Turning it on reruns setup once; the
  shards, pack and MTP layer are reused, so the first start is the mmproj
  download plus the usual expert load (minutes, not the ~92 GB download).
- The engine keeps ~700 MiB of VRAM free for the encoder (`setup.py`
  `VISION["gpu"]["reserve_mib"]`), taken from the expert cache. A picture
  becomes at most 1024 image tokens.
- Hermes sends images natively only to models marked `supports_vision: true`
  under `providers.litellm.models` in
  [`config/config.yaml`](../../development/hermes/config/config.yaml). LiteLLM's
  Strata routes carry the same flag in `model_info`.

```bash
# quick check through LiteLLM (any small PNG)
b64=$(base64 -w0 test.png)
curl -fsS http://litellm-service.litellm.svc.cluster.local:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_API_KEY" -H 'Content-Type: application/json' \
  -d "{\"model\":\"qwen3.8-flash-next\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"What does this image show?\"},{\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/png;base64,$b64\"}}]}]}"
```

Rollback: `VISION=off` (setup reruns, nothing is downloaded).

## Checks

```bash
kubectl -n strata get pods
kubectl -n strata logs deploy/strata-server -c keep-old-paths
kubectl -n strata logs deploy/strata-server
kubectl -n strata port-forward svc/strata-service 18080:8080
curl -fsS http://127.0.0.1:18080/health
curl -fsS http://127.0.0.1:18080/v1/models
```

vLLM is off during the test, so compare against the saved FP8 TP=2 baseline
(`--baseline <results.json>`):
[`benchmarks/ai-realworld-load/tools/README.md`](../../../benchmarks/ai-realworld-load/tools/README.md).

## Batch slots and the gateway

`PARALLEL` in the `strata-settings` ConfigMap is `strata launch --parallel` (upstream
[`docs/BATCHING.md`](https://github.com/Niko1221/Strata/blob/v0.2.11/docs/BATCHING.md)):
up to N requests decode together, more wait. 0.2.x defaults to 8 slots fitted
to the card, so it is always set here. Changing it restarts the pod (experts
reload into RAM, a few minutes) but reruns no download. `GET /v1/status` ->
`concurrency.serving` shows what the engine actually runs (it drops slots that
don't fit in VRAM).

It is **1** (see the comment in `kustomization.yaml`). Earlier 2-slot notes: each slot takes ~0.6 GB of the 18.45 GB expert cache (upstream's
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

Revert the upgrade PR. The 0.1.x image finds its files through the links
`keep-old-paths` left (`/data/models` etc.) and its old `/data/config`, so it
starts without a download. Not tested: whether 0.2.x changes the pack files in
place (0.1.x would then fail to load and need its setup rerun).

Revert the original test PR to remove Strata: vLLM gets both cards back, the `qwen3.8-27b` fallback goes
away and Strata is removed (its PV is `Retain`, so the ~92 GB under `strata/`
on the NVMe stays until deleted by hand).
