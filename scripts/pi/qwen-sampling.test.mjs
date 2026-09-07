import assert from "node:assert/strict";
import test from "node:test";
import install from "./qwen-sampling.ts";

let handler;
install({ on: (event, callback) => {
  assert.equal(event, "before_provider_request");
  handler = callback;
} });
const context = { sessionManager: { getSessionId: () => "session-test" }, model: { provider: "vanillax-vllm", id: "qwen3.8-27b" } };

for (const level of ["low", "medium", "xhigh", "off"]) {
  test(`${level} selects the sampler and preserves agent history`, () => {
    const off = level === "off";
    const payload = {
      chat_template_kwargs: {
        enable_thinking: !off,
        preserve_thinking: !off,
        ...(!off && { reasoning_effort: level }),
      },
      messages: [{ role: "assistant", reasoning: "retained", tool_calls: [] }],
      tools: [{ type: "function", function: { name: "lookup" } }],
      max_tokens: 32768,
      temperature: 9,
    };
    const result = handler({ payload }, context);
    assert.deepEqual(
      [result.temperature, result.top_p, result.top_k, result.min_p,
        result.presence_penalty, result.repetition_penalty],
      off ? [0.7, 0.8, 20, 0, 1.5, 1] : [1, 0.95, 20, 0, 0, 1],
    );
    for (const key of ["messages", "tools", "chat_template_kwargs", "max_tokens"]) {
      assert.equal(result[key], payload[key]);
    }
    assert.equal(payload.temperature, 9);
  });
}

test("other providers and models remain untouched", () => {
  for (const model of [undefined, { ...context.model, provider: "moonshot" },
    { ...context.model, id: "other-model" }]) {
    assert.equal(handler({ payload: { temperature: 0.2 } }, { model }), undefined);
  }
});


test("requests in a Pi session share telemetry metadata without losing caller fields", () => {
  const result = handler({ payload: {} }, context);
  assert.deepEqual(result.metadata, { session_id: "session-test", trace_name: "pi-agent", tags: ["pi"] });
  const metadata = { session_id: "caller-session", tags: ["custom"], trace_user_id: "operator" };
  const overridden = handler({ payload: { metadata } }, context);
  assert.deepEqual(overridden.metadata, { trace_name: "pi-agent", ...metadata });
  assert.deepEqual(metadata.tags, ["custom"]);
});
