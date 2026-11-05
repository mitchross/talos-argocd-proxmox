# ComfyUI on Talos + ArgoCD

GPU-backed image and video generation service. It uses the
[`yanwk/comfyui-boot`](https://github.com/YanWenKun/ComfyUI-Docker) MEGAPAK
image (ComfyUI, about 40 custom nodes, and SageAttention and FlashAttention
pre-compiled for Ampere). It runs on the GPU worker behind
Gateway API.

## How it's wired

```
users → https://comfyui.vanillax.me
     → gateway-external → HTTPRoute: comfyui
     → Service (comfyui-service:8188)
     → Deployment: comfyui  (GPU pod, one replica, Recreate)
            │
            ├── /root  ← PVC: comfyui-storage-smb (SMB RWM, 250Gi, TrueNAS)
            │            ├── ComfyUI/          ← app code + custom nodes
            │            ├── models/           ← shared model repo (share root)
            │            ├── user-scripts/     ← pre-start.sh copied from ConfigMap
            │            └── .download-complete  ← image's first-run marker
            ├── /root/ComfyUI/models ← same PVC, subPath models/ — masks the
            │            legacy dir so downloads land in the shared repo
            ├── /root/ComfyUI/user/__manager/config.ini ← ConfigMap
            └── /opt/custom-nodes (read-only)            ← ConfigMap
```

- Namespace: `comfyui`
- GPU: one full RTX 3090 (Ampere, compute 8.6) via `runtimeClassName: nvidia`, `nvidia.com/gpu: 1`.
- Priority: `gpu-workload-preemptible`. vLLM owns both cards, so ComfyUI stays at zero replicas.
- Strategy: `Recreate`. This is mandatory. RWM SMB allows multi-attach in theory, but the app isn't safe to multi-write.

## Storage model

The PVC is a **static, pre-provisioned SMB PV** pointing at
`//192.168.10.133/comfyui` on TrueNAS (see `pvc.yaml`). It authenticates with
the `smbcreds` secret. SMB replaces NFS so a password protects access instead of an IP allowlist. It is **not** a dynamically provisioned Longhorn
volume. This has four consequences:

- **The 250Gi PVC is a quota and handle.** The real data lives on TrueNAS.
  Deleting and recreating the PVC, or the whole namespace, does **not** delete
  the models. The backing SMB share persists across cluster rebuilds.
- **Models live in the shared repo** at `<share>/models/` (standard ComfyUI
  per-type folders). ComfyUI Desktop on the CachyOS box shares it, mounted
  there at `/mnt/nas/comfyui/models`. The deployment masks it over
  `/root/ComfyUI/models` with a `subPath` mount, so the app and its
  auto-downloader read and write the shared repo directly. The legacy
  NFS-era tree at `<share>/ComfyUI/` still exists, but its models folders
  were emptied into the shared repo (2026-07).
- **`download-models-job.yaml` fills gaps.** The separate one-shot Job
  (`comfyui-download-models`) uses `huggingface_hub` and `HF_TOKEN` to pull
  specific model files to the same shared repo. It is idempotent. The Python
  script checks `os.path.exists(dest)` before downloading. Re-running the
  Job is safe, and it only fetches what's missing.
- **The image's entrypoint also runs on first boot.** On a genuinely empty
  PVC, the `yanwk/comfyui-boot` entrypoint clones ComfyUI, installs custom
  nodes, and downloads a small set of default models. It drops
  `/root/.download-complete` when finished and skips on later boots.
  On this cluster that file already exists on the share, so the entrypoint
  goes straight to launching ComfyUI.

**To reset the models, don't delete the PVC.** SSH into
TrueNAS and clean up `/mnt/ai-pool/comfyui/models/` selectively,
or remove `.download-complete` to force the image's first-run path again.
The models repo is shared with ComfyUI Desktop, so deleting there
deletes for both.

## Files

| File | Purpose |
|------|---------|
| `namespace.yaml` | `comfyui` namespace |
| `pvc.yaml` | Static SMB PV + PVC (250Gi RWM, `smb.csi.k8s.io` driver, `smbcreds` auth) |
| `deployment.yaml` | GPU Deployment, init-container to seed `pre-start.sh`, main container |
| `service.yaml` | ClusterIP with named port `http:8188` (required for HTTPRoute) |
| `httproute.yaml` | External HTTPRoute for `comfyui.vanillax.me` |
| `externalsecret.yaml` | Pulls `HF_TOKEN` from 1Password for the Job and the deployment |
| `configmap.yaml` | Manager `config.ini`, custom-node list, `pre-start.sh` |
| `custom-nodes/` | Extra custom nodes shipped as files (ConfigMap source) |
| `workflows/` | Sample ComfyUI workflows (not auto-loaded, drop into the UI) |
| `download-models-job.yaml` | One-shot HuggingFace downloader (idempotent) |
| `kustomization.yaml` | Ties the files together |

## Container image

```
yanwk/comfyui-boot:cu130-megapak-pt211-20260413@sha256:<digest>
```

- CUDA 13.0 and PyTorch 2.11 (Ampere-optimized).
- Includes ComfyUI, Python 3.12, GCC 11, and about 40 custom nodes pre-installed.
- Pre-compiled attention kernels: SageAttention 2.2.0, FlashAttention 2.8.3, Nunchaku, and SpargeAttention.
- Full CUDA devkit for JIT-compiling PyTorch C++ extensions at node-install time.
- Renovate pins the tag together with an image digest, so `:latest` drift can't change the image.

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
| `TORCH_CUDA_ARCH_LIST`| `8.6`                                                  | RTX 3090 (Ampere). Makes custom-node C++ builds target the right architecture. |
| `CMAKE_ARGS`          | `-DBUILD_opencv_world=ON -DWITH_CUDA=ON -DCUDA_FAST_MATH=ON -DWITH_CUBLAS=ON` | Fast CUDA math for OpenCV-using nodes. |
| `HF_TOKEN`            | from `comfyui-secrets`                                 | HuggingFace gated-model access + the downloader Job. |

### Resources

```
requests: cpu 2,  memory 8Gi,  nvidia.com/gpu 1
limits:   cpu 16, memory 80Gi, nvidia.com/gpu 1
```

The RAM limit is high because big diffusion models hold the VAE and UNet
partially in CPU memory during swap. Don't shrink the limit without
watching for OOM on large-batch runs.

## Deployment

ArgoCD applies this automatically (directory = Application).
For a manual apply in dev or an emergency:

```bash
kubectl apply -k my-apps/ai/comfyui/
```

`infrastructure/gpu/nvidia-gpu-operator/` manages the GPU-node prerequisites
(extensions, device plugin, runtime class). Don't
re-apply them from here.

## Interactions with other apps

- **vLLM** owns both RTX 3090s. ComfyUI stays at zero replicas until a
  deliberate GPU scale-swap. Its caption and text bridge calls LiteLLM with a
  namespace-local External Secret. The bridge normalizes saved legacy local URLs to
  the gateway, and credentials are never saved in workflows.
- **Open WebUI** uses ComfyUI for image generation:
  `COMFYUI_BASE_URL=http://comfyui-service.comfyui.svc.cluster.local:8188`.
  See `my-apps/ai/open-webui/configmap.yaml`.

## Gotchas

- **Don't delete the PVC to "clean up".** The SMB share is shared state.
  Deleting the PVC drops the K8s handle but leaves the data on TrueNAS.
  Recreating the PVC remounts the same data.
- **Manager `config.ini` via `subPath`.** The mount uses `subPath:
  config.ini` because a full directory mount would hide the rest of the
  manager dir.
- **Custom nodes need chmod +x.** That's why an init container copies `pre-start.sh`
  into the PVC. A pure ConfigMap mount is
  read-only, and the image's entrypoint `chmod`s the file.
- **`download-models-job` is a Job with ArgoCD hooks** (`hook: Sync`,
  `hook-delete-policy: BeforeHookCreation`). Without them, a Renovate image
  bump on the Python base would wedge ArgoCD on "Job is immutable".
- **SMB `rsize`/`wsize` 4MiB and `max_credits=64`** set
  model-read throughput on the 10GbE TrueNAS link. Don't drop them unless
  you're debugging CIFS quirks.
