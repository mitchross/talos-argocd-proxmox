# Single-GPU Llama.cpp + ComfyUI Vision Integration

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split dual 3090s so llama-cpp uses 1 GPU with Qwen3.5 Q4_K_XL (only model) and ComfyUI uses the other, with ComfyUI able to call llama-cpp for vision/captioning.

**Architecture:** llama-cpp drops from 2 GPUs to 1, switches from dual-model (Coder + Qwen3.5 Q6) to single-model (Qwen3.5 Q4_K_XL with mmproj for vision). Context reduced to 16K for captioning use case. ComfyUI already has `comfyui-llamacpp-client` node installed and requests 1 GPU — no changes needed to ComfyUI deployment. Both pods schedule on the same GPU node, each claiming 1 of 2 GPUs.

**Tech Stack:** llama.cpp server (CUDA), Qwen3.5-35B-A3B multimodal, ComfyUI, comfyui-llamacpp-client node

---

### Task 1: Update llama-cpp ConfigMap — single Qwen3.5 Q4_K_XL preset

**Files:**
- Modify: `my-apps/ai/llama-cpp/configmap.yaml`

**Step 1: Replace configmap with single-model preset**

Replace entire `data.presets.ini` content with:

```ini
# ==========================================================
# QWEN3.5-35B-A3B [MULTIMODAL] — Single GPU (RTX 3090 24GB)
# ==========================================================
[qwen3.5]
# 35B total / 3B active (MoE) - Gated DeltaNet + Gated Attention
# Natively multimodal (vision + language)
# Q4_K_XL (20.6GB) + mmproj (858MB) fits in single 24GB 3090
# Feb 27 2026: Updated Unsloth Dynamic 2.0 quant (MXFP4 retired from attention)
# Qwen official "precise" thinking params
model = /models/Qwen3.5-35B-A3B-UD-Q4_K_XL.gguf
mmproj = /models/mmproj-F16.gguf
alias = qwen3.5, qwen 3.5, general, vision, image, multimodal, coder, code
ctx-size = 16384
n-gpu-layers = 99
temp = 0.6
top-p = 0.95
top-k = 20
min-p = 0.0
presence-penalty = 0.0
chat-template-kwargs = {"enable_thinking": true}
jinja = 1
```

Key changes:
- Removed Qwen3-Coder-Next preset entirely
- Switched Q6_K_XL → Q4_K_XL
- Removed `tensor-split = 1,1` (single GPU)
- Context 131072 → 16384 (captioning/prompting use case)
- Added `coder, code` aliases so existing API consumers still resolve

---

### Task 2: Update llama-cpp Deployment — single GPU, reduced resources

**Files:**
- Modify: `my-apps/ai/llama-cpp/deployment.yaml`

**Step 1: Update server args**

Change global `-c` from `131072` to `16384`.

Remove `--models-max 8` (only 1 model now — remove or set to `1`).

Remove `-b 4096` and `-ub 1024` (single GPU with smaller context doesn't need oversized batches). Replace with `-b 2048` and `-ub 512`.

Keep: `--models-preset`, `-ngl 99`, `-fa on`, `--jinja`, `--fit on`, `--no-mmap`, `--cache-type-k q8_0`, `--cache-type-v q8_0`, `--parallel 1`, `--host`, `--port`.

**Step 2: Update env vars for single GPU**

```yaml
env:
  - name: NVIDIA_VISIBLE_DEVICES
    value: "all"
  - name: CUDA_VISIBLE_DEVICES
    value: "0"
  - name: NVIDIA_DRIVER_CAPABILITIES
    value: "compute,utility"
  - name: GGML_CUDA_ENABLE_UNIFIED_MEMORY
    value: "1"
```

Remove:
- `GGML_CUDA_PEER_MAX_BATCH_SIZE` (multi-GPU peer transfer, not needed)
- `CUDA_SCALE_LAUNCH_QUEUES` (multi-GPU launch queue optimization, not needed)

**Step 3: Update resource requests/limits**

```yaml
resources:
  limits:
    cpu: "32"
    memory: 64Gi        # Q4_K_XL (20.6GB) + KV cache + overhead, RAM for expert paging
    nvidia.com/gpu: "1"  # Was 2
    ephemeral-storage: "50Gi"
  requests:
    cpu: "8"
    memory: 32Gi
    nvidia.com/gpu: "1"  # Was 2
    ephemeral-storage: "10Gi"
```

**Step 4: Reduce /dev/shm**

Change `sizeLimit: 32Gi` → `sizeLimit: 8Gi` (single GPU, smaller context).

**Step 5: Update comments**

- `terminationGracePeriodSeconds: 300` comment → update from "400GB memory unmapping" to "model unload time"
- `GGML_CUDA_ENABLE_UNIFIED_MEMORY` comment → update to reference single 3090

---

### Task 3: Create vision captioning workflow for ComfyUI

**Files:**
- Create: `my-apps/ai/comfyui/workflows/qwen35-vision-caption.json`

This workflow: Load Image → LlamaCpp Client (vision) → Show Text

The `comfyui-llamacpp-client` node needs the llama-cpp service URL:
`http://llama-cpp-service.llama-cpp.svc.cluster.local:8080`

Note: The exact class_type and parameter names depend on the installed version of `comfyui-llamacpp-client`. The workflow should be created in the ComfyUI UI and exported, or verified against the node's actual parameter schema. Create a minimal reference workflow:

```json
{
  "1": {
    "class_type": "LoadImage",
    "inputs": {
      "image": "input.png"
    }
  },
  "2": {
    "class_type": "LlamaCppClient",
    "inputs": {
      "server_url": "http://llama-cpp-service.llama-cpp.svc.cluster.local:8080",
      "endpoint": "/v1/chat/completions",
      "prompt": "Describe this image in detail for use as a Stable Diffusion prompt. Focus on composition, lighting, colors, style, and subject matter.",
      "image": ["1", 0],
      "temperature": 0.6,
      "top_p": 0.95,
      "top_k": 20,
      "max_tokens": 512
    }
  },
  "3": {
    "class_type": "ShowText|pysssss",
    "inputs": {
      "text": ["2", 0]
    }
  }
}
```

**Important:** This workflow JSON is a reference template. The actual node class_type and input names must be verified from the installed `comfyui-llamacpp-client` node in the ComfyUI UI. The user may need to recreate it visually in ComfyUI to match the actual node interface.

---

### Task 4: Update ComfyUI pre-start to copy vision workflow

**Files:**
- Modify: `my-apps/ai/comfyui/configmap.yaml` (the `comfyui-pre-start` ConfigMap)

**Step 1: Add workflow copy to pre-start.sh**

After the WanVideoWrapper workflow copy section, add:

```bash
# ── LlamaCpp Vision Workflows ────────────────────────────
# Copy from ConfigMap-mounted workflows (if available)
LLAMA_WF="/opt/workflows/qwen35-vision-caption.json"
if [ -f "$LLAMA_WF" ]; then
  cp -f "$LLAMA_WF" "$DEST/" && \
    echo "[INFO] Copied Qwen3.5 vision captioning workflow" || true
fi
```

**Step 2: Mount workflow as ConfigMap in ComfyUI deployment**

Create a new ConfigMap from the workflow JSON and mount it, OR simply document that the workflow should be loaded manually in the ComfyUI UI.

Given that workflows are typically created/edited in the UI and the JSON structure needs verification against the actual node, the simpler approach is: **skip auto-deployment** and have the user create the workflow in ComfyUI UI using these parameters:
- Server URL: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080`
- Endpoint: `/v1/chat/completions`
- Model alias: `qwen3.5` (or any alias from the preset)

This avoids fragile JSON that might not match the node's actual schema.

**Decision: Skip Task 3 and Task 4.** The workflow JSON depends on the exact node interface which is better created in the UI. Document the connection URL instead.

---

### Task 5: Commit and verify

**Step 1: Commit changes**

```bash
git add my-apps/ai/llama-cpp/configmap.yaml my-apps/ai/llama-cpp/deployment.yaml
git commit -m "feat(llama-cpp): single GPU Qwen3.5 Q4_K_XL, free GPU for ComfyUI

- Drop from 2 GPUs to 1 (frees RTX 3090 for ComfyUI)
- Remove Qwen3-Coder-Next model, use only Qwen3.5-35B-A3B
- Switch Q6_K_XL → Q4_K_XL (20.6GB fits in single 24GB 3090)
- Reduce context 131K → 16K (captioning/prompting use case)
- Remove multi-GPU env vars and tensor-split
- Reduce memory/CPU requests for single-model single-GPU"
```

**Step 2: Verify after ArgoCD sync**

```bash
# Check both pods are running (each on 1 GPU)
kubectl get pods -n llama-cpp
kubectl get pods -n comfyui

# Verify llama-cpp loaded model
kubectl logs -n llama-cpp -l app=llama-cpp-server --tail=50

# Verify GPU allocation (should show 1 GPU each)
kubectl describe node <gpu-node> | grep -A5 "Allocated resources"

# Test vision API
kubectl run -it --rm curl --image=curlimages/curl --restart=Never -- \
  curl http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/health
```

**Step 3: Configure ComfyUI llamacpp-client node**

In ComfyUI UI:
1. Add "LlamaCpp Client" node from AI/LlamaCpp category
2. Set server URL: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080`
3. Connect a LoadImage node to its image input
4. Set prompt: "Describe this image in detail for use as a Stable Diffusion prompt"
5. Connect output to text display or directly to a prompt input
