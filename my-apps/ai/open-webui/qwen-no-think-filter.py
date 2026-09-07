"""Apply explicit Qwen reasoning and mode-specific sampling to WebUI requests."""

from typing import Optional


class Filter:
    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        if body.get("model") != "qwen3.8-27b":
            return body

        extra_body = body.setdefault("extra_body", {})
        # Canonical kwargs win conflicts; normalize both possible forwarding paths.
        kwargs = {**extra_body.get("chat_template_kwargs", {}),
                  **body.get("chat_template_kwargs", {})}
        effort = kwargs.get("reasoning_effort",
                            body.get("reasoning_effort", extra_body.get("reasoning_effort")))
        enabled = kwargs.get("enable_thinking", effort not in ("none", "off"))
        if not isinstance(enabled, bool):
            raise ValueError("enable_thinking must be a boolean")
        kwargs["enable_thinking"] = enabled
        kwargs.setdefault("preserve_thinking", enabled)
        if not isinstance(kwargs["preserve_thinking"], bool):
            raise ValueError("preserve_thinking must be a boolean")
        if enabled:
            effort = "medium" if effort in (None, "high") else effort
            if effort not in ("low", "medium", "xhigh"):
                raise ValueError("Qwen reasoning effort must be low, medium, or xhigh")
            kwargs["reasoning_effort"] = effort
        else:
            kwargs.pop("reasoning_effort", None)

        sampler = dict(temperature=1.0 if enabled else 0.7,
                       top_p=0.95 if enabled else 0.8, top_k=20, min_p=0.0,
                       presence_penalty=0.0 if enabled else 1.5, repetition_penalty=1.0)
        for target in (body, extra_body):
            # Block WebUI's later fill-if-absent from restoring a stale effort.
            target["reasoning_effort"] = kwargs.get("reasoning_effort")
            target["chat_template_kwargs"] = dict(kwargs)
            target.update(sampler)

        return body
