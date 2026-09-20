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
  for (const model of [undefined, { ...context.model, provider: "vanillax-openrouter", id: "deepseek-flash" },
    { ...context.model, provider: "vanillax-auto", id: "pi-auto" },
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


test("direct OpenRouter bypasses gateway telemetry and sampling", () => {
  const payload = { messages: [], reasoning: { effort: "high" }, max_tokens: 32768 };
  const result = handler({ payload }, { ...context, model: {
    provider: "vanillax-direct-openrouter", id: "~deepseek/deepseek-flash-latest",
  } });
  assert.equal(result, payload);
  assert.equal("metadata" in result, false);
});

test("requests in a Pi session share telemetry metadata without losing caller fields", () => {
  const result = handler({ payload: {} }, context);
  assert.deepEqual(result.metadata, { session_id: "session-test", trace_name: "pi-agent", tags: ["pi"] });
  const metadata = { session_id: "caller-session", tags: ["custom"], trace_user_id: "operator" };
  const overridden = handler({ payload: { metadata } }, context);
  assert.deepEqual(overridden.metadata, { trace_name: "pi-agent", ...metadata });
  assert.deepEqual(metadata.tags, ["custom"]);
});

const image = (id) => ({ type: "image_url", image_url: { url: `data:image/png;base64,${id}` } });
const images = (payload) => payload.messages.flatMap((m) => Array.isArray(m.content) ? m.content : [])
  .filter((part) => part.type === "image_url");
function freeze(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}

for (const model of [context.model, { provider: "vanillax-auto", id: "pi-auto" }]) {
  test(`${model.id}: resumed screenshot/tool history keeps newest image without altering session`, () => {
    const newest = image("newest");
    const payload = freeze({
      messages: [
        { role: "system", content: "Instructions" },
        { role: "user", content: [image("old"), { type: "text", text: "Inspect this" }] },
        { role: "assistant", content: null, reasoning_content: "Observation", tool_calls: [
          { id: "read1", type: "function", function: { name: "read", arguments: "{}" } },
        ] },
        { role: "tool", tool_call_id: "read1", content: "Image read" },
        { role: "user", content: [image("old"), newest] },
        { role: "user", content: "almost better" },
      ],
      tools: [{ type: "function", function: { name: "read" } }],
      stream: true, stream_options: { include_usage: true }, temperature: 0.2,
    });
    const before = JSON.stringify(payload);
    const result = handler({ payload }, { ...context, model });
    assert.deepEqual(images(result), [newest]);
    assert.equal(JSON.stringify(payload), before);
    assert.equal(result.messages[2], payload.messages[2]);
    assert.equal(result.messages[3], payload.messages[3]);
    assert.equal(result.messages[5], payload.messages[5]);
    assert.equal(result.tools, payload.tools);
    assert.equal(result.stream_options, payload.stream_options);
    assert.match(result.messages[1].content[0].text, /Only the newest image is visible/);
    assert.deepEqual(handler({ payload: result }, { ...context, model }), result);
    if (model.id === "pi-auto") assert.equal(result.temperature, 0.2);
  });

  test(`${model.id}: repeated reads of one attachment send it once`, () => {
    const same = image("same");
    const payload = { messages: [{ role: "user", content: [same, same, same] }] };
    assert.deepEqual(images(handler({ payload }, { ...context, model })), [same]);
  });

  test(`${model.id}: zero or one image preserves messages`, () => {
    for (const content of ["text", [], [image("one")]]) {
      const payload = { messages: [{ role: "user", content }] };
      assert.equal(handler({ payload }, { ...context, model }).messages, payload.messages);
    }
  });
}

test("explicit cloud and unrelated routes retain multiple images", () => {
  for (const model of [
    { provider: "vanillax-openrouter", id: "deepseek-flash" },
    { provider: "vanillax-direct-openrouter", id: "~deepseek/deepseek-flash-latest" },
    { provider: "other", id: "pi-auto" },
    { provider: "vanillax-vllm", id: "other" },
  ]) {
    const payload = { messages: [{ role: "user", content: [image("a"), image("b")] }] };
    assert.equal(handler({ payload }, { ...context, model }).messages, payload.messages);
  }
});
