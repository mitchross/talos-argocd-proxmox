import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function newestImageOnly(payload: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(payload.messages)) return payload;
  const originalMessages = payload.messages;
  let remaining = 1;
  // Work on the serialized request only; never remove images from Pi's saved session.
  const messages = originalMessages.slice();
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (!Array.isArray(message.content)) continue;
    const content = message.content.slice();
    let changed = false;
    for (let j = content.length - 1; j >= 0; j--) {
      if (content[j]?.type !== "image_url") continue;
      if (remaining > 0) {
        remaining--;
        continue;
      }
      content[j] = {
        type: "text",
        text: "[Earlier image omitted from this request: local Qwen/pi-auto permits one image. Only the newest image is visible; use prior text observations or re-read the needed image.]",
      };
      changed = true;
    }
    if (changed) messages[i] = { ...message, content };
  }
  return messages.some((message, i) => message !== originalMessages[i])
    ? { ...payload, messages } : payload;
}

// Pi's thinking toggle changes template kwargs, but does not switch Qwen's sampler.
export default function (pi: ExtensionAPI) {
  pi.on("before_provider_request", (event, ctx) => {
    const local = ctx.model?.provider === "vanillax-vllm" && ctx.model.id === "qwen3.8-27b";
    const auto = ctx.model?.provider === "vanillax-auto" && ctx.model.id === "pi-auto";
    const original = event.payload as Record<string, unknown>;
    const payload = local || auto ? newestImageOnly(original) : original;
    if (ctx.model?.provider === "vanillax-direct-openrouter") return payload;
    // Keep direct and auto-routed requests in the same Langfuse session.
    const traced = {
      ...payload,
      metadata: {
        session_id: ctx.sessionManager.getSessionId(),
        trace_name: "pi-agent",
        tags: ["pi"],
        ...(payload.metadata as Record<string, unknown> | undefined),
      },
    };
    if (!local) return traced;
    const kwargs = payload.chat_template_kwargs as Record<string, unknown> | undefined;
    const off = kwargs?.enable_thinking === false;
    return {
      ...traced,
      temperature: off ? 0.7 : 1.0,
      top_p: off ? 0.8 : 0.95,
      top_k: 20,
      min_p: 0.0,
      presence_penalty: off ? 1.5 : 0.0,
      repetition_penalty: off ? 1.0 : 1.05,
    };
  });
}
