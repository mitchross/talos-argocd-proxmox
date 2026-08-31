"""Force the local Qwen3.8-27B backend into non-thinking mode.

Open WebUI can add/forward per-request reasoning controls that override the
vLLM server default. Keep the everyday qwen3.8-27b model deterministic here:
normal chat/tool/vision requests should use the non-thinking template unless
we intentionally create a separate thinking model/profile later.
"""

from typing import Optional


class Filter:
    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        if body.get("model") != "qwen3.8-27b":
            return body

        chat_template_kwargs = body.setdefault("chat_template_kwargs", {})
        chat_template_kwargs["enable_thinking"] = False

        # Open WebUI may also carry provider-specific options in extra_body.
        # Mirror the setting there so the OpenAI-compatible forwarding path
        # cannot re-enable thinking downstream.
        extra_body = body.setdefault("extra_body", {})
        extra_chat_template_kwargs = extra_body.setdefault("chat_template_kwargs", {})
        extra_chat_template_kwargs["enable_thinking"] = False

        return body
