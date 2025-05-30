#!/bin/bash

# ComfyUI Setup Script for Kubernetes with GPU
# This script sets up ComfyUI with popular models and workflows

set -e

echo "🚀 Setting up ComfyUI on Kubernetes with GPU support..."

# Apply the manifests
kubectl apply -f comfyui-manifests.yaml

# Wait for deployment to be ready
echo "⏳ Waiting for ComfyUI deployment to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/comfyui -n comfyui

# Get the pod name
POD_NAME=$(kubectl get pods -n comfyui -l app=comfyui -o jsonpath='{.items[0].metadata.name}')

echo "📦 Installing ComfyUI Manager and essential custom nodes for latest models..."
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git
git clone https://github.com/cubiq/ComfyUI_essentials.git
git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git
git clone https://github.com/rgthree/rgthree-comfy.git
# Flux-specific nodes
git clone https://github.com/kijai/ComfyUI-FluxTrainer.git
git clone https://github.com/city96/ComfyUI-GGUF.git
# Additional useful nodes
git clone https://github.com/WASasquatch/was-node-suite-comfyui.git
git clone https://github.com/jags111/efficiency-nodes-comfyui.git
"

echo "🤖 Downloading latest and greatest models from CivitAI and Hugging Face..."

# Create model directories
kubectl exec -n comfyui $POD_NAME -- bash -c "
mkdir -p /opt/ComfyUI/models/checkpoints
mkdir -p /opt/ComfyUI/models/unet 
mkdir -p /opt/ComfyUI/models/vae
mkdir -p /opt/ComfyUI/models/clip
mkdir -p /opt/ComfyUI/models/embeddings
"

# Download Flux Dev (Full BF16 version for maximum quality with 24GB VRAM)
echo "📥 Downloading Flux Dev BF16 (taking advantage of your 24GB VRAM)..."
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/unet
wget -O flux1-dev.safetensors 'https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors'
# Also keep FP8 version as backup for complex workflows
wget -O flux1-dev-fp8.safetensors 'https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8.safetensors'
"

# Download Flux Schnell for faster generation
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/unet
wget -O flux1-schnell.safetensors 'https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors'
"

# Download Flux VAE
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/vae
wget -O ae.safetensors 'https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors'
"

# Download Flux Text Encoders (Full precision for 24GB setup)
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/clip
wget -O t5xxl_fp16.safetensors 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors'
wget -O t5xxl_fp8_e4m3fn.safetensors 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors'
wget -O clip_l.safetensors 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors'
"

# Download CyberRealistic Pony (latest version)
echo "📥 Downloading CyberRealistic Pony..."
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/checkpoints
wget -O cyberrealistic_pony_v11.safetensors 'https://civitai.com/api/download/models/951667'
"

# Download SDXL Base (still useful)
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/checkpoints
wget -O sd_xl_base_1.0.safetensors https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
"

# Download SDXL VAE
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/vae
wget -O sdxl_vae.safetensors https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors
"

# Download popular embeddings for better prompting
kubectl exec -n comfyui $POD_NAME -- bash -c "
cd /opt/ComfyUI/models/embeddings
wget -O cyberrealistic_negative_pony.pt 'https://civitai.com/api/download/models/83425'
wget -O cyberrealistic_positive_pony.pt 'https://civitai.com/api/download/models/1729052'
"

# Download latest ControlNet models
kubectl exec -n comfyui $POD_NAME -- bash -c "
mkdir -p /opt/ComfyUI/models/controlnet
cd /opt/ComfyUI/models/controlnet
wget -O control_v11p_sd15_canny.pth https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_canny.pth
wget -O control_v11p_sd15_openpose.pth https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_openpose.pth
# Flux ControlNet models
wget -O flux-dev-controlnet-canny-v3.safetensors 'https://huggingface.co/XLabs-AI/flux-controlnet-canny-v3/resolve/main/flux-controlnet-canny-v3.safetensors'
wget -O flux-dev-controlnet-depth-v3.safetensors 'https://huggingface.co/XLabs-AI/flux-controlnet-depth-v3/resolve/main/flux-controlnet-depth-v3.safetensors'
"

# Download upscaler models
kubectl exec -n comfyui $POD_NAME -- bash -c "
mkdir -p /opt/ComfyUI/models/upscale_models
cd /opt/ComfyUI/models/upscale_models
wget -O RealESRGAN_x4plus.pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
wget -O RealESRGAN_x4plus_anime_6B.pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth
"

echo "📋 Setting up workflows for latest models..."

# Create advanced workflows directory
kubectl exec -n comfyui $POD_NAME -- bash -c "
mkdir -p /opt/ComfyUI/user/default/workflows
"

# Create Flux Dev workflow
kubectl exec -n comfyui $POD_NAME -- bash -c "
cat > /opt/ComfyUI/user/default/workflows/flux_dev_workflow.json << 'EOF'
{
  \"1\": {
    \"inputs\": {
      \"text\": \"a beautiful portrait of a woman, photorealistic, highly detailed, professional photography, studio lighting\"
    },
    \"class_type\": \"CLIPTextEncode\",
    \"_meta\": {
      \"title\": \"CLIP Text Encode (Prompt)\"
    }
  },
  \"2\": {
    \"inputs\": {
      \"unet_name\": \"flux1-dev-fp8.safetensors\",
      \"weight_dtype\": \"fp8_e4m3fn\"
    },
    \"class_type\": \"UNETLoader\",
    \"_meta\": {
      \"title\": \"Load Diffusion Model\"
    }
  },
  \"3\": {
    \"inputs\": {
      \"clip_name1\": \"t5xxl_fp8_e4m3fn.safetensors\",
      \"clip_name2\": \"clip_l.safetensors\",
      \"type\": \"flux\"
    },
    \"class_type\": \"DualCLIPLoader\",
    \"_meta\": {
      \"title\": \"DualCLIPLoader\"
    }
  },
  \"4\": {
    \"inputs\": {
      \"vae_name\": \"ae.safetensors\"
    },
    \"class_type\": \"VAELoader\",
    \"_meta\": {
      \"title\": \"Load VAE\"
    }
  },
  \"5\": {
    \"inputs\": {
      \"width\": 1024,
      \"height\": 1024,
      \"batch_size\": 1
    },
    \"class_type\": \"EmptyLatentImage\",
    \"_meta\": {
      \"title\": \"Empty Latent Image\"
    }
  },
  \"6\": {
    \"inputs\": {
      \"seed\": 42,
      \"steps\": 20,
      \"cfg\": 3.5,
      \"sampler_name\": \"euler\",
      \"scheduler\": \"simple\",
      \"denoise\": 1.0,
      \"model\": [\"2\", 0],
      \"positive\": [\"1\", 0],
      \"negative\": [\"\", 0],
      \"latent_image\": [\"5\", 0]
    },
    \"class_type\": \"KSampler\",
    \"_meta\": {
      \"title\": \"KSampler\"
    }
  },
  \"7\": {
    \"inputs\": {
      \"samples\": [\"6\", 0],
      \"vae\": [\"4\", 0]
    },
    \"class_type\": \"VAEDecode\",
    \"_meta\": {
      \"title\": \"VAE Decode\"
    }
  },
  \"8\": {
    \"inputs\": {
      \"filename_prefix\": \"Flux_Dev\",
      \"images\": [\"7\", 0]
    },
    \"class_type\": \"SaveImage\",
    \"_meta\": {
      \"title\": \"Save Image\"
    }
  }
}
EOF
"

# Create CyberRealistic Pony workflow
kubectl exec -n comfyui $POD_NAME -- bash -c "
cat > /opt/ComfyUI/user/default/workflows/cyberrealistic_pony_workflow.json << 'EOF'
{
  \"1\": {
    \"inputs\": {
      \"text\": \"score_9, score_8_up, score_7_up, realistic, 1girl, beautiful woman, portrait, professional photography, studio lighting, detailed face, perfect skin, cyberrealistic_positive_pony\"
    },
    \"class_type\": \"CLIPTextEncode\",
    \"_meta\": {
      \"title\": \"CLIP Text Encode (Prompt)\"
    }
  },
  \"2\": {
    \"inputs\": {
      \"text\": \"score_6, score_5, score_4, blurry, low quality, distorted, cyberrealistic_negative_pony\"
    },
    \"class_type\": \"CLIPTextEncode\",
    \"_meta\": {
      \"title\": \"CLIP Text Encode (Negative)\"
    }
  },
  \"3\": {
    \"inputs\": {
      \"seed\": 42,
      \"steps\": 25,
      \"cfg\": 7.0,
      \"sampler_name\": \"dpmpp_2m_sde\",
      \"scheduler\": \"karras\",
      \"denoise\": 1.0,
      \"model\": [\"4\", 0],
      \"positive\": [\"1\", 0],
      \"negative\": [\"2\", 0],
      \"latent_image\": [\"5\", 0]
    },
    \"class_type\": \"KSampler\",
    \"_meta\": {
      \"title\": \"KSampler\"
    }
  },
  \"4\": {
    \"inputs\": {
      \"ckpt_name\": \"cyberrealistic_pony_v11.safetensors\"
    },
    \"class_type\": \"CheckpointLoaderSimple\",
    \"_meta\": {
      \"title\": \"Load Checkpoint\"
    }
  },
  \"5\": {
    \"inputs\": {
      \"width\": 832,
      \"height\": 1216,
      \"batch_size\": 1
    },
    \"class_type\": \"EmptyLatentImage\",
    \"_meta\": {
      \"title\": \"Empty Latent Image\"
    }
  },
  \"6\": {
    \"inputs\": {
      \"samples\": [\"3\", 0],
      \"vae\": [\"4\", 2]
    },
    \"class_type\": \"VAEDecode\",
    \"_meta\": {
      \"title\": \"VAE Decode\"
    }
  },
  \"7\": {
    \"inputs\": {
      \"filename_prefix\": \"CyberRealistic_Pony\",
      \"images\": [\"6\", 0]
    },
    \"class_type\": \"SaveImage\",
    \"_meta\": {
      \"title\": \"Save Image\"
    }
  }
}
EOF
"

# Restart ComfyUI to pick up new models and nodes
echo "🔄 Restarting ComfyUI to load new components..."
kubectl rollout restart deployment/comfyui -n comfyui
kubectl wait --for=condition=available --timeout=300s deployment/comfyui -n comfyui

# Get service info
echo "✅ ComfyUI setup complete!"
echo ""
echo "🌐 Access Information:"
echo "Internal Service: comfyui-service.comfyui.svc.cluster.local:8188"

# Check if NodePort service exists
if kubectl get service comfyui-nodeport -n comfyui &>/dev/null; then
    NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
    if [ -z "$NODE_IP" ]; then
        NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
    fi
    echo "NodePort Access: http://$NODE_IP:30188"
fi

# Port forward option
echo ""
echo "💡 To access via port forward:"
echo "kubectl port-forward -n comfyui service/comfyui-service 8188:8188"
echo "Then open: http://localhost:8188"

echo ""
echo "📁 Available workflows:"
echo "  - flux_dev_workflow.json (Flux Dev FP8 for high-quality photorealistic images)"
echo "  - cyberrealistic_pony_workflow.json (CyberRealistic Pony for versatile realistic images)"
echo "🛠️  ComfyUI Manager is installed for easy model and node management"
echo ""
echo "🎯 Latest models included:"
echo "  - Flux Dev FP8 (12B parameter model for exceptional quality)"
echo "  - CyberRealistic Pony v11 (Popular photorealistic model)"
echo "  - SDXL Base 1.0 (Stable foundation model)"
echo "  - Flux & SDXL VAEs"
echo "  - Flux ControlNet (Canny, Depth)"
echo "  - Traditional ControlNet (Canny, OpenPose)"
echo "  - RealESRGAN Upscalers (General & Anime)"
echo "  - CyberRealistic embeddings for better prompting"
echo ""
echo "💡 Pro Tips:"
echo "  - Use Flux Dev for highest quality photorealistic images"
echo "  - Use CyberRealistic Pony for versatile realistic content"
echo "  - Flux works best with simpler prompts and lower CFG (3.5-4.0)"
echo "  - CyberRealistic Pony benefits from score_9, score_8_up tags"
echo "  - Use the embeddings for better prompt results"