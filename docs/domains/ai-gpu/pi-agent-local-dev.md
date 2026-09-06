# Pi.dev agent on the dual-3090 backend

Current workstation guide, audited 2026-09-06 against Pi **0.84.2**, its installed
provider source, and the live LiteLLM → vLLM endpoint. Pi is the coding agent from
[pi.dev](https://pi.dev), not Raspberry Pi. These files configure a workstation;
cluster changes still go through Git and ArgoCD.

Use **`vanillax-vllm/qwen3.8-27b`, medium thinking, preserved reasoning, native
vision, and automatic compaction**. Keep the existing provider identity and
cloud providers. The audit found a stale `qwen3.6-27b` default and the built-in
`qwen-chat-template` toggle, which omitted the selected reasoning effort.

## Provider configuration

Back up `~/.pi/agent/models.json`, `settings.json`, and `AGENTS.md` before editing.
Merge this provider into `models.json`; do not overwrite other providers or
credentials. Use `/login` for `vanillax-vllm` and enter the LiteLLM key from
1Password (`homelab-prod/litellm/master_key`). Pi stores it in workstation
`auth.json`; omit `apiKey` from the provider JSON. A placeholder key fails
against this authenticated gateway. Keep credentials out of Git.

```json
{
  "providers": {
    "vanillax-vllm": {
      "baseUrl": "https://litellm.vanillax.me/v1",
      "api": "openai-completions",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false,
        "supportsUsageInStreaming": true,
        "maxTokensField": "max_tokens",
        "thinkingFormat": "chat-template",
        "chatTemplateKwargs": {
          "enable_thinking": { "$var": "thinking.enabled" },
          "reasoning_effort": {
            "$var": "thinking.effort",
            "omitWhenOff": true
          },
          "preserve_thinking": { "$var": "thinking.enabled" }
        }
      },
      "models": [
        {
          "id": "qwen3.8-27b",
          "name": "Qwen3.8 27B (vLLM FP8, 2x3090, 262K)",
          "reasoning": true,
          "thinkingLevelMap": {
            "off": "off",
            "minimal": null,
            "low": "low",
            "medium": "medium",
            "high": null,
            "xhigh": "xhigh",
            "max": null
          },
          "input": ["text", "image"],
          "contextWindow": 262144,
          "maxTokens": 32768,
          "cost": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0
          }
        }
      ]
    }
  }
}
```

`thinkingFormat: chat-template` resolves Pi's selected thinking level into
Qwen's native kwargs. `supportsReasoningEffort: false` prevents a conflicting
top-level field. The model-level mapping exposes only supported choices:

| Pi level | Thinking | Effort sent | Preserve reasoning |
|---|---|---|---|
| off | false | omitted | false |
| low | true | low | true |
| medium (normal coding) | true | medium | true |
| xhigh (explicit difficult task) | true | xhigh | true |

Qwen accepts no `high` value. Unsupported Pi levels are `null`, so the selector
skips them. Upstream Qwen defaults to xhigh when effort is omitted; explicit
client mapping and the server's medium fallback prevent that accident.
Preservation is on for agent continuity and unchanged-prefix reuse. Stateless
chats may explicitly disable preservation without changing the server default.
[Official Qwen controls](https://huggingface.co/Qwen/Qwen3.8-27B-FP8#api-usage),
[Pi model schema](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md).

Requests pass through LiteLLM for Prometheus metrics and PostHog AI analytics.
The provider ID stays `vanillax-vllm`, preserving its thinking mapping and sampler
extension. The backend is still stock vLLM with the same context and GPUs.
[Telemetry verification and direct-access fallback](ai-observability.md) explains
how to confirm actual event storage; successful inference alone is insufficient.

## Settings and usable context

Merge these fields into `~/.pi/agent/settings.json`; keep packages, other model
preferences, authentication, and UI settings:

```json
{
  "defaultProvider": "vanillax-vllm",
  "defaultModel": "qwen3.8-27b",
  "defaultThinkingLevel": "medium",
  "modelThinkingLevels": {
    "vanillax-vllm/qwen3.8-27b": "medium"
  },
  "compaction": {
    "enabled": true,
    "reserveTokens": 49152,
    "keepRecentTokens": 20000
  }
}
```

The **262,144-token window includes input, tool schemas/results, images,
reasoning, and the answer**. `maxTokens: 32768` is the output budget, not an
extra window. Pi compacts when estimated context exceeds the window minus
`reserveTokens`: approximately **212,992 tokens** here. The 49,152 reserve is
our operating recommendation: 32,768 output tokens plus 16,384 for tool growth.
It leaves the full server ceiling available while starting cleanup before a
long tool result exhausts it. This is not an upstream-required value or a
hard protection against arbitrarily large tool output. Compaction settings are
global in Pi; smaller cloud models may need a project-specific override.

Compaction summarizes older history and retains a recent tail. It is lossy:
keep task decisions, file paths, verification results, and remaining work in
a concise handoff. Use `/compact` at milestones and `/new` between unrelated
tasks. Avoid whole-repository dumps; search and read relevant sections.
[Pi compaction behavior](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/compaction.md),
[settings and project overrides](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md).

Two GPU cards do not mean two independent model servers. The live shared pool
holds about 325K tokens; two simultaneous 262K sessions do not fit. Use one
long coding session near the ceiling. A second light request can share the
pool, but parallel agent fanout competes for the same capacity. See the
[measured capacity audit](3090-llm-optimization.md).

## Correct sampling when switching thinking off

Pi's template mapping switches reasoning but does not switch sampling.
The small repo-owned
[Qwen sampler extension](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/pi/qwen-sampling.ts)
uses Pi's `before_provider_request` hook to select Qwen's six recommended
sampling values after serialization. It applies only to
`vanillax-vllm/qwen3.8-27b`, leaves messages/tools/template mapping intact, and
sets mode-specific values even if a stale client temperature was selected.

From the repository root, back up any existing copy, then install:

```bash
mkdir -p ~/.pi/agent/extensions
cp scripts/pi/qwen-sampling.ts ~/.pi/agent/extensions/qwen-sampling.ts
```

Restart Pi or use `/reload`. Thinking requests use temperature 1.0, top-p 0.95,
top-k 20, min-p 0, presence penalty 0, repetition penalty 1. Off requests use
0.7, 0.8, 20, 0, 1.5, 1 respectively. The server-wide thinking sampler stays
unchanged. Without this extension, Pi off still disables reasoning, but needs
another per-request sampler override to match Qwen's recommendation.
[Pi request hook](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md#before_provider_request),
[canonical server policy and API examples](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md#explicit-reasoning-and-sampling).

## Vision and browser tools

The current server permits **one image in the entire submitted request** and
no video. Pi can resend images from earlier turns: one new screenshot plus an
old screenshot can already exceed the limit. This is unrelated to the size of
the text context window. Keep text/DOM extraction as the browser default and
use a screenshot when visual evidence is needed.

If the image limit is reached, do not blindly retry. Start `/new` with a text
handoff and the required image. `/compact` can help only if the old image is in
the portion discarded; a recent image may remain. Do not promise that compaction
always resets the image count. Keep this rule in workstation `AGENTS.md`.

## Recommended agent tools

Start with Pi's built-in file and shell tools. Use the existing LSP integration
for symbol/type diagnostics, a web tool for current documentation, and browser
DevTools when the task needs a logged-in page. Keep installed packages; avoid
adding overlapping tool suites just because the context window is larger.
Inspect `/session` and tool output growth during long work. Small, relevant
outputs preserve room for reasoning and reduce prefill work.

Use a new session for clean validation; resumed sessions may retain their old
model or thinking level. No provider rename, shell alias, or Pi upgrade is
required for this configuration. The audited Homebrew installation is 0.84.2;
update through its package manager separately when needed.

## Verification and rollback

```bash
pi --version
pi --list-models qwen3.8-27b
pi --provider vanillax-vllm --model qwen3.8-27b --thinking medium
```

Expected: `vanillax-vllm`, `qwen3.8-27b`, roughly 262K context and 32K output,
with thinking and image support. Start normally with `pi` after setting the
defaults. Use `/model` to reload model metadata and select low, medium, xhigh,
or off explicitly.

For an isolated smoke request from the repo root:

```bash
pi --no-session --no-extensions --no-skills --no-prompt-templates \
  --no-context-files --no-tools -e ./scripts/pi/qwen-sampling.ts \
  --provider vanillax-vllm --model qwen3.8-27b --thinking medium \
  -p 'What is 37 times 43? Give the answer.'
```

Expected answer: 1591. Repeat with `--thinking low`, `xhigh`, and `off`.
Inspect the emitted request when validating effort: answer length does not
prove the selected mode. The [server acceptance matrix](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md#reasoning-acceptance-checks)
also covers tool calls, images, and multi-turn reasoning. Streaming usage must
be present so Pi can track context; do not disable it to hide an API error.

For offline policy checks (Node 24+ and Python with PyYAML):

```bash
node --test scripts/pi/qwen-sampling.test.mjs
uv run --with pyyaml python -m unittest discover -s scripts/tests -p test_qwen_reasoning.py -v
```

The September audit also exercised the installed Pi serializer against a local
HTTP capture server: default/low/medium/xhigh/off produced the expected kwargs,
sampler and usage request. A real medium request through the LAN endpoint
returned 1591 with separate reasoning and streaming token counts. Those checks
validate plumbing, not agent task quality.

To roll back workstation changes, restore the backed-up JSON/AGENTS files and
remove the newly installed sampler extension (or restore its previous copy),
then restart Pi. No Kubernetes rollback is needed for workstation files.
For server-policy rollback, revert the reasoning-policy commit through Git.
