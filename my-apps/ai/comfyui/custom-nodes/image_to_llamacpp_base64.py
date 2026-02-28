"""Bridge node: converts ComfyUI IMAGE tensor to base64 JSON for LlamaCppClient."""

import base64
import io
import json

import numpy as np
from PIL import Image


class ImageToLlamaCppBase64:
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
        # IMAGE tensor shape: [batch, height, width, channels] float32 0-1
        img_array = (image[0].cpu().numpy() * 255).astype(np.uint8)
        pil_image = Image.fromarray(img_array)

        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

        image_data = json.dumps([{"data": f"data:image/png;base64,{b64_str}", "id": 1}])
        user_message = f"[img-1] {prompt}"

        return (image_data, user_message)


NODE_CLASS_MAPPINGS = {
    "ImageToLlamaCppBase64": ImageToLlamaCppBase64,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageToLlamaCppBase64": "Image to LlamaCpp Base64",
}
