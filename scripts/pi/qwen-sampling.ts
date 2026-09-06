import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Pi's thinking toggle changes template kwargs, but does not switch Qwen's sampler.
export default function (pi: ExtensionAPI) {
  pi.on("before_provider_request", (event, ctx) => {
    if (ctx.model?.provider !== "vanillax-vllm" || ctx.model.id !== "qwen3.8-27b") return;
    const payload = event.payload as Record<string, unknown>;
    const kwargs = payload.chat_template_kwargs as Record<string, unknown> | undefined;
    const off = kwargs?.enable_thinking === false;
    return {
      ...payload,
      temperature: off ? 0.7 : 1.0,
      top_p: off ? 0.8 : 0.95,
      top_k: 20,
      min_p: 0.0,
      presence_penalty: off ? 1.5 : 0.0,
      repetition_penalty: 1.0,
    };
  });
}
