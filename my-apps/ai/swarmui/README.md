# SwarmUI

SwarmUI ([mcmonkeyprojects/SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI))
is a .NET frontend/orchestrator over ComfyUI. It **replaces the standalone
`comfyui` app** in this cluster: `my-apps/ai/comfyui` is scaled to
`replicas: 0` and SwarmUI self-starts its own managed ComfyUI on **GPU 1**.

## Why this shape

- **No official image.** `jasonacox/swarmui:0.9.7` is a clean, unmodified build
  of SwarmUI's own `launchtools/StandardDockerfile.docker` — the only community
  image that is both current and tracked. Pinned by digest, watched by Renovate.
- **GPU.** Same whole-card pattern as the old comfyui app. There is no spare
  GPU in this cluster (time-slicing is deliberately disabled), which is why
  comfyui had to be retired rather than run alongside.
- **Models are reused, not re-downloaded.** `swarmui-comfyui-models` is a static
  NFS PV pointing at the *same* TrueNAS share the old comfyui used
  (`192.168.10.133:/mnt/ai-pool/comfyui`), mounted at `/comfyui-models`.
- **Storage.** `Data` + `Output` are Longhorn with `backup: "daily"`;
  `dlbackend` (SwarmUI's auto-installed ComfyUI + torch venv) is Longhorn with
  **no** backup label because it is fully reinstallable.

## One-time bootstrap (required, ~10–15 min)

Pre-seeding `Settings.fds` would skip the install wizard but would **not**
install ComfyUI into `dlbackend/` — the backend would then error forever. So we
let SwarmUI's wizard run **once** via the web UI; it installs ComfyUI into the
persistent `swarmui-dlbackend` PVC and writes its own `Data/Settings.fds` +
`Data/Backends.fds`. Every restart after that is GitOps-stable — no manifest
changes, no scripts.

After ArgoCD syncs the app and the pod is running:

1. Open `https://swarmui.vanillax.me` (LAN only).
2. In the install wizard:
   - **Backend**: choose **ComfyUI Self-Starting** (the default).
   - **Models**: when asked, **skip** the model download — models already
     exist on the NFS share.
   - Finish the wizard. SwarmUI installs ComfyUI + torch into `dlbackend`
     (several minutes; the UI stays up).
3. Point SwarmUI at the existing models: **Server → Server Configuration**
   - `Paths.ModelRoot` = `/comfyui-models/ComfyUI/models`
   - `Paths.SDModelFolder` = `checkpoints` (ComfyUI-style folder naming)
   - Save, then **Refresh Models**.
4. (Recommended) **Server → Server Configuration**: disable
   "Check for Updates" so the GitOps-pinned image stays authoritative.

Config now persists in the `swarmui-data` PVC. To re-run the wizard from
scratch, delete the `swarmui-data` (and `swarmui-dlbackend`) PVCs.

## Reverting to standalone ComfyUI

Set `my-apps/ai/comfyui/deployment.yaml` back to `replicas: 1` and scale
SwarmUI down (`replicas: 0`). They cannot both run — only one whole GPU.
