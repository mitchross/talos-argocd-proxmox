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
      repetition_penalty: 1.2,
    };
    const result = handler({ payload }, context);
    assert.deepEqual(
      [result.temperature, result.top_p, result.top_k, result.min_p,
        result.presence_penalty, result.repetition_penalty],
      off ? [0.7, 0.8, 20, 0, 1.5, 1] : [1, 0.95, 20, 0, 0, 1.05],
    );
    for (const key of ["messages", "tools", "chat_template_kwargs", "max_tokens"]) {
      assert.equal(result[key], payload[key]);
    }
    assert.equal(payload.temperature, 9);
    assert.equal(payload.repetition_penalty, 1.2);
  });
}

test("omitted kwargs use the thinking policy without changing template defaults", () => {
  const payload = { repetition_penalty: 1.0 };
  const result = handler({ payload }, context);
  assert.equal(result.repetition_penalty, 1.05);
  assert.equal(result.temperature, 1.0);
  assert.equal("chat_template_kwargs" in result, false);
  assert.deepEqual(payload, { repetition_penalty: 1.0 });
});

test("switching off and back on does not retain the previous mode's penalty", () => {
  let payload = { chat_template_kwargs: { enable_thinking: true, reasoning_effort: "medium" } };
  for (const enabled of [true, false, true]) {
    payload = { ...payload, chat_template_kwargs: { enable_thinking: enabled } };
    payload = handler({ payload }, context);
    assert.equal(payload.repetition_penalty, enabled ? 1.05 : 1.0);
  }
});

test("other providers and models keep their sampler but still get traced", () => {
  for (const model of [undefined, { ...context.model, provider: "vanillax-litellm", id: "kimi-k3" },
    { ...context.model, id: "other-model" }]) {
    const result = handler({ payload: { temperature: 0.2 } },
      { ...context, model });
    assert.equal(result.temperature, 0.2);
    for (const key of ["top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty"]) {
      assert.equal(key in result, false);
    }
    assert.deepEqual(result.metadata, { session_id: "session-test", trace_name: "pi-agent", tags: ["pi"] });
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
