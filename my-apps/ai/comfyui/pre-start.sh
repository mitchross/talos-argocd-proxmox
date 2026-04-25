#!/bin/bash
set -eu

# ── Git Config ─────────────────────────────────────────────
git config --global core.fileMode false || true

# ── Custom Node Management ─────────────────────────────────
# Clone only if missing. Updates are done via ComfyUI Manager UI.
install_node() {
  local repo="$1"
  local name
  name="$(basename "$repo" .git)"
  local dest="/root/ComfyUI/custom_nodes/$name"

  if [ -d "$dest" ]; then
    echo "[SKIP] $name already installed"
  elif [ -d "/root/ComfyUI/custom_nodes" ]; then
    echo "[INFO] Installing $name..."
    git clone --depth 1 "$repo" "$dest"
  fi
}

echo "[INFO] Managing custom nodes..."
install_node "https://github.com/FranckyB/ComfyUI-Prompt-Manager.git"
install_node "https://github.com/kijai/ComfyUI-WanVideoWrapper.git"
install_node "https://github.com/PanicTitan/ComfyUI-Gallery.git"
install_node "https://github.com/fidecastro/comfyui-llamacpp-client.git"
install_node "https://github.com/mit-han-lab/ComfyUI-nunchaku.git"
install_node "https://github.com/Zlata-Salyukova/Comfy-Canvas.git"
install_node "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"
install_node "https://github.com/welltop-cn/ComfyUI-TeaCache.git"
install_node "https://github.com/ltdrdata/ComfyUI-Inspire-Pack.git"
# Provides NunchakuQwenImageLoraStackV3 used by QuantFunc's Qwen SVDQ workflows.
# Upstream mit-han-lab/ComfyUI-nunchaku only ships the Flux LoRA nodes, not Qwen.
install_node "https://github.com/ussoewwin/ComfyUI-QwenImageLoraLoader.git"
# Provides EsesImageCompare used by the Flux2 Klein 9B Ultimate v2.1 workflow.
install_node "https://github.com/quasiblob/ComfyUI-EsesImageCompare.git"

# ── Python Dependencies ────────────────────────────────────
# Install base deps into py3.13 explicitly (same as nunchaku / frontend_package / custom-node deps below).
# Default `uv pip install --system` targets py3.12 which ComfyUI doesn't use,
# so colorama/watchdog etc. would be invisible to the custom-node imports.
# This is why ComfyUI-Prompt-Manager ("No module named 'colorama'") and
# ComfyUI-Gallery ("No module named 'watchdog'") were failing to import.
PY313=/usr/bin/python3.13
echo "[INFO] Installing Python dependencies into py3.13..."
$PY313 -m pip install --no-cache-dir --root-user-action=ignore \
  transformers "bitsandbytes>=0.46.1" \
  colorama huggingface_hub \
  watchdog piexif aiohttp \
  pywavelets

# $PY313 was defined above. Compute cp-tag for nunchaku wheel.
PYTAG="cp$($PY313 -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor}")')"

# Nunchaku SVDQ runtime wheel (CUDA 13.0 + PyTorch 2.11, Ampere+)
# Required for ComfyUI-nunchaku node to load Qwen-Image / Qwen-Image-Edit SVDQ int4 weights.
echo "[INFO] Installing nunchaku wheel into py3.13 (${PYTAG})..."
if ! $PY313 -c "import nunchaku" 2>/dev/null; then
  $PY313 -m pip install --no-cache-dir --root-user-action=ignore \
    "https://github.com/nunchaku-ai/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu13.0torch2.11-${PYTAG}-${PYTAG}-linux_x86_64.whl"
else
  echo "[SKIP] nunchaku already installed in py3.13"
fi

# Custom-node Python requirements — install into py3.13 so ComfyUI can import them.
echo "[INFO] Installing custom-node deps into py3.13..."
for d in Comfy-Canvas ComfyUI-nunchaku ComfyUI_IPAdapter_plus ComfyUI-TeaCache ComfyUI-Inspire-Pack ComfyUI-QwenImageLoraLoader; do
  req="/root/ComfyUI/custom_nodes/$d/requirements.txt"
  if [ -f "$req" ]; then
    $PY313 -m pip install --no-cache-dir --root-user-action=ignore -r "$req" 2>&1 | tail -2 || true
  fi
done

# Pin comfyui_frontend_package to the backend's recommended patch (1.42.11).
# The megapak image ships 1.42.10, which produces a "Failed to load subgraph
# blueprints" error on newer WanVideoWrapper example workflows. Upgrading
# past the backend's supported line (e.g. 1.43.x) breaks Vue bootstrap
# entirely ("Loading Error — A required resource failed to load") because
# ComfyUI backend 0.19.x isn't on that major yet — so we pin exactly.
# Bump this when the backend (via megapak image) moves forward.
echo "[INFO] Pinning comfyui_frontend_package==1.42.11 in py3.13..."
$PY313 -m pip install --no-cache-dir --root-user-action=ignore "comfyui_frontend_package==1.42.11" 2>&1 | tail -2 || true

# ── Opinionated UI defaults (GitOps-reproducible) ──────────
# Merges specific keys into /root/ComfyUI/user/default/comfy.settings.json
# without touching any other keys you've set via the UI. Runs every boot,
# so changes here take effect on pod restart. Remove a key from the merge
# block to let the UI fully own it again.
SETTINGS=/root/ComfyUI/user/default/comfy.settings.json
mkdir -p "$(dirname $SETTINGS)"
[ -f "$SETTINGS" ] || echo "{}" > "$SETTINGS"
$PY313 <<'PYSETTINGS'
import json, pathlib
p = pathlib.Path("/root/ComfyUI/user/default/comfy.settings.json")
data = json.loads(p.read_text() or "{}")
overrides = {
    # Hide API pricing badges on cloud nodes — this cluster runs fully local.
    "Comfy.NodeBadge.ShowApiPricing": False,
    # Live sampler preview using tiny autoencoder — keeps generation interactive.
    "Comfy.Execution.PreviewMethod": "taesd",
}
changed = False
for k, v in overrides.items():
    if data.get(k) != v:
        data[k] = v
        changed = True
        print(f"[settings] {k} = {v}")
if changed:
    p.write_text(json.dumps(data, indent=4))
else:
    print("[settings] already up-to-date")
PYSETTINGS

# ── System Setup ───────────────────────────────────────────
mkdir -p /usr/share/fonts/truetype

# ── Bridge Nodes (from ConfigMap) ─────────────────────────
echo "[INFO] Installing bridge nodes..."
cp /opt/custom-nodes/image_to_llamacpp_base64.py \
   /root/ComfyUI/custom_nodes/image_to_llamacpp_base64.py

# ── Example Workflows ──────────────────────────────────────
DEST="/root/ComfyUI/user/default/workflows"
mkdir -p "$DEST"
SRC="/root/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper/example_workflows"
if [ -d "$SRC" ]; then
  cp -f "$SRC"/*.json "$DEST/" 2>/dev/null && \
    echo "[INFO] Copied Wan 2.2 example workflows" || true
fi

echo "[INFO] Pre-start setup complete."
