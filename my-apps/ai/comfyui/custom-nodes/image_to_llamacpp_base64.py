"""Bridge nodes for LlamaCpp vision integration in ComfyUI."""

import base64
import io
import json
import re
import urllib.request
import urllib.error

import numpy as np
from PIL import Image

_DEFAULT_SERVER = "http://llama-cpp-service.llama-cpp.svc.cluster.local:8080"
_DEFAULT_MODEL = "qwen3.6 - qwen3.6-35b-a3b"


def _image_to_base64(image_tensor):
    """Convert ComfyUI IMAGE tensor [B,H,W,C] to base64 PNG string."""
    img_array = (image_tensor[0].cpu().numpy() * 255).astype(np.uint8)
    pil_image = Image.fromarray(img_array)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _chat_completion(server_url, model, messages, temperature, max_tokens):
    """Call llama.cpp /v1/chat/completions and return the text response."""
    payload = {
        "model": model,
        "messages": messages,
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
        return f"[ERROR {e.code}] {body[:500]}"
    except Exception as e:
        return f"[ERROR] {e}"

    # With enable_thinking=true, llama.cpp separates thinking into reasoning_content
    # and the actual answer into content. Only use content.
    choice = result.get("choices", [{}])[0]
    message = choice.get("message", {})
    text = message.get("content", "").strip()
    if not text:
        # Fallback: if content is empty, try reasoning_content
        text = message.get("reasoning_content", "").strip()
    if not text:
        text = json.dumps(result)
    # Safety net: strip any <think> blocks that leak through
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return text


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
    """Sends an image to a llama.cpp vision model and returns the caption text."""

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
                "server_url": ("STRING", {"default": _DEFAULT_SERVER}),
                "model": ("STRING", {"default": _DEFAULT_MODEL}),
                "temperature": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.1}),
                "max_tokens": ("INT", {"default": 4096, "min": 64, "max": 8192, "step": 64}),
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
        server_url=_DEFAULT_SERVER,
        model=_DEFAULT_MODEL,
        temperature=0.6,
        max_tokens=4096,
    ):
        b64_str = _image_to_base64(image)
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_str}"}},
        ]
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content},
        ]
        return (_chat_completion(server_url, model, messages, temperature, max_tokens),)


class LlamaCppTextModify:
    """Takes a text prompt and modification instructions, returns the modified prompt.

    Use this to edit AI-generated captions before image generation:
    VisionCaption -> TextModify -> CLIPTextEncode
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_text": ("STRING", {"forceInput": True}),
                "instructions": (
                    "STRING",
                    {
                        "default": "Make it cyberpunk style with neon lighting",
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "server_url": ("STRING", {"default": _DEFAULT_SERVER}),
                "model": ("STRING", {"default": _DEFAULT_MODEL}),
                "temperature": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.1}),
                "max_tokens": ("INT", {"default": 4096, "min": 64, "max": 8192, "step": 64}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("modified_text",)
    FUNCTION = "modify"
    CATEGORY = "AI/LlamaCpp"

    def modify(
        self,
        original_text,
        instructions="Make it cyberpunk style with neon lighting",
        server_url=_DEFAULT_SERVER,
        model=_DEFAULT_MODEL,
        temperature=0.6,
        max_tokens=4096,
    ):
        messages = [
            {
                "role": "system",
                "content": "You modify image generation prompts. Apply the requested changes "
                "to the original prompt. Keep all unmentioned details. "
                "Output ONLY the modified prompt text.",
            },
            {
                "role": "user",
                "content": f"Original prompt: {original_text}\n\nChanges: {instructions}",
            },
        ]
        return (_chat_completion(server_url, model, messages, temperature, max_tokens),)


NODE_CLASS_MAPPINGS = {
    "ImageToLlamaCppBase64": ImageToLlamaCppBase64,
    "LlamaCppVisionCaption": LlamaCppVisionCaption,
    "LlamaCppTextModify": LlamaCppTextModify,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageToLlamaCppBase64": "Image to LlamaCpp Base64",
    "LlamaCppVisionCaption": "LlamaCpp Vision Caption",
    "LlamaCppTextModify": "LlamaCpp Text Modify",
}
