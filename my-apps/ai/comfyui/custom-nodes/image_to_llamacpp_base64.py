"""Bridge nodes for LlamaCpp vision integration in ComfyUI."""

import base64
import io
import json
import urllib.request
import urllib.error

import numpy as np
from PIL import Image


def _image_to_base64(image_tensor):
    """Convert ComfyUI IMAGE tensor [B,H,W,C] to base64 PNG string."""
    img_array = (image_tensor[0].cpu().numpy() * 255).astype(np.uint8)
    pil_image = Image.fromarray(img_array)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class ImageToLlamaCppBase64:
    """Converts ComfyUI IMAGE tensor to base64 JSON for LlamaCppClient node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
            },
            "optional": {
                "prompt": (
                    "STRING",
                    {
                        "default": "Describe this image in rich detail for use as an image generation prompt. "
                        "Focus on subject, composition, lighting, colors, style, and mood. "
                        "Output only the prompt text, no preamble.",
                        "multiline": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("image_data", "user_message")
    FUNCTION = "convert"
    CATEGORY = "AI/LlamaCpp"

    def convert(
        self,
        image,
        prompt="Describe this image in rich detail for use as an image generation prompt. "
        "Focus on subject, composition, lighting, colors, style, and mood. "
        "Output only the prompt text, no preamble.",
    ):
        b64_str = _image_to_base64(image)
        image_data = json.dumps([{"data": f"data:image/png;base64,{b64_str}", "id": 1}])
        user_message = f"[img-1] {prompt}"
        return (image_data, user_message)


class LlamaCppVisionCaption:
    """Sends an image to a llama.cpp vision model and returns the caption text.

    Bypasses the LlamaCppClient node to avoid dict/string response bugs.
    Calls /v1/chat/completions directly with proper image content blocks.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
            },
            "optional": {
                "prompt": (
                    "STRING",
                    {
                        "default": "Describe this image in rich detail for use as an image generation prompt. "
                        "Focus on subject, composition, lighting, colors, style, and mood. "
                        "Output only the prompt text, no preamble.",
                        "multiline": True,
                    },
                ),
                "system_message": (
                    "STRING",
                    {
                        "default": "You are an expert image description assistant. Produce a detailed, vivid "
                        "text-to-image prompt that would recreate the given image. Include subject, setting, "
                        "lighting, colors, composition, artistic style, and mood. Output ONLY the prompt text.",
                        "multiline": True,
                    },
                ),
                "server_url": (
                    "STRING",
                    {"default": "http://llama-cpp-service.llama-cpp.svc.cluster.local:8080"},
                ),
                "model": ("STRING", {"default": "general - qwen3.5"}),
                "temperature": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.1}),
                "max_tokens": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 64}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("caption",)
    FUNCTION = "caption"
    CATEGORY = "AI/LlamaCpp"

    def caption(
        self,
        image,
        prompt="Describe this image in rich detail for use as an image generation prompt. "
        "Focus on subject, composition, lighting, colors, style, and mood. "
        "Output only the prompt text, no preamble.",
        system_message="You are an expert image description assistant. Produce a detailed, vivid "
        "text-to-image prompt that would recreate the given image. Include subject, setting, "
        "lighting, colors, composition, artistic style, and mood. Output ONLY the prompt text.",
        server_url="http://llama-cpp-service.llama-cpp.svc.cluster.local:8080",
        model="general - qwen3.5",
        temperature=0.6,
        max_tokens=1024,
    ):
        b64_str = _image_to_base64(image)

        # Prepend /no_think to skip Qwen3.5 reasoning and go straight to content
        user_content = [
            {"type": "text", "text": f"/no_think {prompt}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_str}"}},
        ]

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        url = f"{server_url.rstrip('/')}/v1/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return (f"[ERROR {e.code}] {body[:500]}",)
        except Exception as e:
            return (f"[ERROR] {e}",)

        # Extract content, falling back to reasoning_content if content is empty
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        text = message.get("content", "").strip()
        if not text:
            text = message.get("reasoning_content", "").strip()
        if not text:
            text = json.dumps(result)

        return (text,)


NODE_CLASS_MAPPINGS = {
    "ImageToLlamaCppBase64": ImageToLlamaCppBase64,
    "LlamaCppVisionCaption": LlamaCppVisionCaption,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageToLlamaCppBase64": "Image to LlamaCpp Base64",
    "LlamaCppVisionCaption": "LlamaCpp Vision Caption",
}
