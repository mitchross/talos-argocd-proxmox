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

# Install into ComfyUI's Python 3.13; uv --system otherwise targets Python 3.12 and imports fail.
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

# Keep comfyui_frontend_package on the backend-supported patch; newer frontend lines can break startup.
echo "[INFO] Pinning comfyui_frontend_package==1.42.11 in py3.13..."
$PY313 -m pip install --no-cache-dir --root-user-action=ignore "comfyui_frontend_package==1.42.11" 2>&1 | tail -2 || true

# Merge these UI defaults on every boot, preserving other keys; remove a key here to let the UI own it.
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
