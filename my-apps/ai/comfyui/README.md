# ComfyUI on Talos + ArgoCD

GPU-backed image/video generation service. Built on the
[`yanwk/comfyui-boot`](https://github.com/YanWenKun/ComfyUI-Docker) MEGAPAK
image (ComfyUI + 40-ish custom nodes + SageAttention / FlashAttention
pre-compiled for Ampere), running on the GPU worker and served behind
Gateway API.

## How it's wired

```
users → https://comfyui.vanillax.me
     → gateway-external → HTTPRoute: comfyui
     → Service (comfyui-service:8188)
     → Deployment: comfyui  (GPU pod, one replica, Recreate)
            │
            ├── /root  ← PVC: comfyui-storage (NFS RWM, 250Gi, TrueNAS)
            │            ├── ComfyUI/          ← app code + custom nodes
            │            ├── ComfyUI/models/   ← models live here (pre-loaded + Job-downloaded)
            │            ├── user-scripts/     ← pre-start.sh copied from ConfigMap
            │            └── .download-complete  ← image's first-run marker
            ├── /root/ComfyUI/user/__manager/config.ini ← ConfigMap
            └── /opt/custom-nodes (read-only)            ← ConfigMap
```

- **Namespace:** `comfyui`
- **GPU:** one full RTX 3090 (Ampere, compute 8.6) via `runtimeClassName: nvidia`, `nvidia.com/gpu: 1`.
- **Priority:** `gpu-workload-preemptible` — llama-cpp preempts this when it needs the GPU back.
- **Strategy:** `Recreate` (mandatory — RWM NFS is fine for multi-attach in theory, but the app isn't safe to multi-write).

## Storage model — important

The PVC is a **static, pre-provisioned NFS PV** pointing at
`192.168.10.133:/mnt/ai-pool/comfyui` on TrueNAS (see `pvc.yaml`). It is
**not** a dynamically provisioned Longhorn volume. Implications:

- **The 250Gi PVC is just a quota/handle** — the real data lives on TrueNAS.
  Deleting + recreating the PVC (or the whole namespace) does **not** delete
  the models. The backing NFS share is persistent across cluster rebuilds.
- **Models are pre-loaded.** The NFS share already holds diffusion models
  (Z-Image-Turbo, Qwen-Image-Edit, Wan 2.2, etc.) from prior runs. New
  pods see them immediately at `/root/ComfyUI/models/…`.
- **`download-models-job.yaml` fills gaps.** The separate one-shot Job
  (`comfyui-download-models`) uses `huggingface_hub` + `HF_TOKEN` to pull
  specific model files to the same NFS share. It's idempotent — the Python
  script checks `os.path.exists(dest)` before downloading. Re-running the
  Job is safe; it only fetches what's missing.
- **The image's entrypoint also runs on first boot.** On a genuinely empty
  PVC, `yanwk/comfyui-boot`'s entrypoint clones ComfyUI, installs custom
  nodes, and downloads a small set of default models. It drops
  `/root/.download-complete` when finished and skips on subsequent boots.
  On this cluster that file already exists on NFS, so the entrypoint
  short-circuits straight to launching ComfyUI.

**If you ever need to "reset" the models:** don't delete the PVC — SSH into
TrueNAS and clean up `/mnt/ai-pool/comfyui/ComfyUI/models/` selectively,
or remove `.download-complete` to force the image's first-run path again.

## Files

| File | Purpose |
|------|---------|
| `namespace.yaml` | `comfyui` namespace |
| `pvc.yaml` | Static NFS PV + PVC (250Gi RWM, `nfs.csi.k8s.io` driver, `nconnect=16`) |
| `deployment.yaml` | GPU Deployment, init-container to seed `pre-start.sh`, main container |
| `service.yaml` | ClusterIP with named port `http:8188` (required for HTTPRoute) |
| `httproute.yaml` | External HTTPRoute → `comfyui.vanillax.me` |
| `externalsecret.yaml` | Pulls `HF_TOKEN` from 1Password for the Job + the deployment |
| `configmap.yaml` | Manager `config.ini`, custom-node list, `pre-start.sh` |
| `custom-nodes/` | Extra custom nodes shipped as files (ConfigMap source) |
| `workflows/` | Sample ComfyUI workflows (not auto-loaded — drop into UI) |
| `download-models-job.yaml` | One-shot HuggingFace downloader (idempotent) |
| `kustomization.yaml` | Ties it all together |

## Container image

```
yanwk/comfyui-boot:cu130-megapak-pt211-20260413@sha256:<digest>
```

- **CUDA 13.0**, **PyTorch 2.11** (Ampere-optimized).
- Includes ComfyUI + Python 3.12 + GCC 11 + 40-ish custom nodes pre-installed.
- Pre-compiled attention kernels: **SageAttention 2.2.0**, **FlashAttention 2.8.3**, **Nunchaku**, **SpargeAttention**.
- Full CUDA devkit for JIT-compiling PyTorch C++ extensions at node-install time.
- Renovate-pinned — the tag is bumped with an image-digest pin so `:latest` drift can't bite you.

### Attention compat (this image)

| GPU Architecture         | SageAttention | FlashAttention | xFormers |
|--------------------------|:-------------:|:--------------:|:--------:|
| Blackwell (RTX 5090)     | ✔️ | ✔️ | ✔️ |
| Ada Lovelace (RTX 4090)  | ✔️ | ✔️ | ✔️ |
| Ampere (RTX 3090)        | ✔️ | ✔️ | ✔️ |
| Turing (RTX 2080)        | ❌ | ❌ | ✔️ |

### Env the deployment sets

| Var                   | Value                                                  | Why |
|-----------------------|--------------------------------------------------------|-----|
| `CLI_ARGS`            | *(empty)*                                              | Image entrypoint already passes `--listen --port 8188 --enable-manager --enable-manager-legacy-ui`. |
| `TORCH_CUDA_ARCH_LIST`| `8.6`                                                  | RTX 3090 (Ampere) — ensures custom-node C++ builds target the right arch. |
| `CMAKE_ARGS`          | `-DBUILD_opencv_world=ON -DWITH_CUDA=ON -DCUDA_FAST_MATH=ON -DWITH_CUBLAS=ON` | Fast CUDA math for OpenCV-using nodes. |
| `HF_TOKEN`            | from `comfyui-secrets`                                 | HuggingFace gated-model access + the downloader Job. |

### Resources

```
requests: cpu 2,  memory 8Gi,  nvidia.com/gpu 1
limits:   cpu 16, memory 80Gi, nvidia.com/gpu 1
```

RAM headroom is generous because big diffusion models hold the VAE/UNet
partially in CPU memory during swap. Don't shrink the limit without
watching for OOM on large-batch runs.

## Deployment

Normally ArgoCD applies this automatically (directory = Application).
Manual apply (dev / emergency):

```bash
kubectl apply -k my-apps/ai/comfyui/
```

The GPU-node prereqs (extensions, device plugin, runtime class) are
managed by `infrastructure/controllers/nvidia-gpu-operator/` — don't
re-apply them from here.

## Interactions with other apps

- **llama-cpp** lives on the same GPU worker. Its `gpu-workload-high`
  priority class preempts ComfyUI's `gpu-workload-preemptible` if both
  try to claim the GPU at the same time. If ComfyUI suddenly dies with
  SIGTERM during an LLM burst, that's why — it's intentional.
- **Open WebUI** uses ComfyUI for image generation:
  `COMFYUI_BASE_URL=http://comfyui-service.comfyui.svc.cluster.local:8188`.
  See `my-apps/ai/open-webui/configmap.yaml`.

## Gotchas

- **Don't delete the PVC to "clean up".** The NFS share is shared state —
  deleting the PVC drops the K8s handle but leaves the data on TrueNAS.
  Recreating the PVC remounts the same data.
- **Manager `config.ini` via `subPath`.** The mount uses `subPath:
  config.ini` because a full directory mount would hide the rest of the
  manager dir.
- **Custom nodes need chmod +x.** That's why `pre-start.sh` is copied
  into the PVC by an init container — a pure ConfigMap mount is
  read-only, and the image's entrypoint `chmod`s the file.
- **`download-models-job` is a Job with ArgoCD hooks** (`hook: Sync`,
  `hook-delete-policy: BeforeHookCreation`) — otherwise a Renovate image
  bump on the Python base would wedge ArgoCD on "Job is immutable".
- **NFS `nconnect=16`** is load-bearing for model-read throughput on the
  10GbE TrueNAS link. Don't drop it unless you're debugging NFS quirks.
