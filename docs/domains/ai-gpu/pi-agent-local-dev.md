# Pi.dev Agent — local coding against Qwen3.8-27B

> **Git-declared cutover:** official Qwen3.8-27B FP8 on stock vLLM v0.28.0,
> two RTX 3090s, FP8 KV, vision and a 262,144-token ceiling. Speculation is off.
> Merge, Argo reconciliation and runtime checks must finish before increasing
> workstation context metadata. The last live backend was llama.cpp at 65K.
> The LAN endpoint stays `https://llama.vanillax.me/v1`.
>
> This document is for **Pi.dev / Pi coding agent**, not Raspberry Pi.

Pi is a workstation client. Nothing in `~/.pi/agent/` deploys to Kubernetes.
The cluster owns model/runtime tuning; Pi only needs provider/model metadata
that describes the OpenAI-compatible API and Qwen3.8's reasoning controls.

## 1. Update Pi

```bash
pi update --self
pi update --all
pi --version
```

`pi update --self` updates Pi itself; `pi update --all` updates Pi and installed
packages/extensions. The configuration below targets Pi 0.84.x or newer.

## 2. `~/.pi/agent/models.json`

Use a dedicated custom provider for the stable local inference endpoint:

```json
{
  "providers": {
    "vanillax-llama": {
      "baseUrl": "https://llama.vanillax.me/v1",
      "api": "openai-completions",
      "apiKey": "local-no-key-required",
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
          "preserve_thinking": true
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
          "maxTokens": 16384,
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

### Why the explicit chat-template mapping matters

Qwen3.8's upstream template accepts only `low`, `medium`, and `xhigh` when
thinking is enabled, and defaults to `xhigh` if effort is omitted. Turning
thinking off is a separate `enable_thinking=false` control.

Pi has a built-in `qwen-chat-template` mode for the on/off toggle, but the
current implementation does not also place Pi's selected effort inside the
Qwen chat-template kwargs. `chat-template` lets this provider send both pieces
explicitly:

| Pi level | `chat_template_kwargs` sent to the backend |
|---|---|
| `off` | `enable_thinking: false`, `preserve_thinking: true` |
| `low` | `enable_thinking: true`, `reasoning_effort: low`, `preserve_thinking: true` |
| `medium` | `enable_thinking: true`, `reasoning_effort: medium`, `preserve_thinking: true` |
| `xhigh` | `enable_thinking: true`, `reasoning_effort: xhigh`, `preserve_thinking: true` |

`omitWhenOff` prevents Pi from sending the string `off` as a Qwen reasoning
effort. Unsupported Pi levels are `null`, so the UI skips them rather than
inventing values the model template rejects.

Other compatibility choices:

- `supportsDeveloperRole: false` keeps the agent context in an ordinary system
  message for the local OpenAI-compatible server.
- `supportsReasoningEffort: false` prevents a duplicate top-level
  `reasoning_effort`; effort is deliberately carried in `chat_template_kwargs`.
- `input: ["text", "image"]` enables Pi screenshot/image input.
- Sampling is not set in Pi. The validated production server owns temp/top-p/
  top-k/min-p/presence/repeat defaults.

`models.json` reloads whenever `/model` is opened.

## 3. Fix your existing `~/.pi/agent/settings.json`

Your current file already has the right packages and uses model-specific
`medium` reasoning. Keep those. Rename the old provider and make the current
backend the default.

The relevant result should be:

```json
{
  "defaultProvider": "vanillax-llama",
  "defaultModel": "qwen3.8-27b",
  "defaultThinkingLevel": "medium",
  "modelThinkingLevels": {
    "vanillax-llama/qwen3.8-27b": "medium"
  },
  "enabledModels": [
    "vanillax-llama/qwen3.8-27b",
    "vanillax-litellm/kimi-k3"
  ]
}
```

Do **not** overwrite your whole file with that small example; preserve your
`packages`, theme, changelog state, and other settings. Update the existing JSON
safely with `jq`:

```bash
cp ~/.pi/agent/settings.json ~/.pi/agent/settings.json.bak

jq '
  .defaultProvider = "vanillax-llama"
  | .defaultModel = "qwen3.8-27b"
  | .defaultThinkingLevel = "medium"
  | .modelThinkingLevels = ((.modelThinkingLevels // {})
      | with_entries(
          if .key == "vanillax-vllm/qwen3.8-27b"
          then .key = "vanillax-llama/qwen3.8-27b"
          else . end))
  | .modelThinkingLevels["vanillax-llama/qwen3.8-27b"] = "medium"
  | .enabledModels = ((.enabledModels // [])
      | map(if . == "vanillax-vllm/qwen3.8-27b"
            then "vanillax-llama/qwen3.8-27b"
            else . end)
      | unique)
' ~/.pi/agent/settings.json > ~/.pi/agent/settings.json.new \
  && mv ~/.pi/agent/settings.json.new ~/.pi/agent/settings.json
```

Then verify:

```bash
jq '{defaultProvider,defaultModel,defaultThinkingLevel,modelThinkingLevels,enabledModels,packages}' \
  ~/.pi/agent/settings.json
```

Current Pi supports both `defaultThinkingLevel` and per-model
`modelThinkingLevels`; keeping the per-model value means this Qwen model starts
at medium even if another provider later uses a different global default.

## 4. Workstation launchers (`~/.zshrc`)

The workstation uses two convenience aliases:

```bash
alias pi-qwen-only='pi --model vanillax-llama/qwen3.8-27b --thinking medium'
alias pi-withk3='pi --model vanillax-litellm/kimi-k3'
```

`pi-qwen-only` always starts a fresh Qwen session on the local vLLM backend
with medium reasoning. `pi-withk3` starts on Kimi K3 through LiteLLM; because
both models remain enabled in Pi settings, `/model` can still switch that
session to `vanillax-llama/qwen3.8-27b` when needed.

Persist the aliases in `~/.zshrc`, then reload the shell:

```bash
source ~/.zshrc

type pi-qwen-only
type pi-withk3
```

Expected:

```text
pi-qwen-only is an alias for pi --model vanillax-llama/qwen3.8-27b --thinking medium
pi-withk3 is an alias for pi --model vanillax-litellm/kimi-k3
```

If an existing Pi session was created before the provider rename, resuming it
may still show `vanillax-vllm` in the status bar because the session metadata
stores the old provider identity. That does **not** mean the new provider config
failed. Use a new session for clean backend validation rather than reusing an
old `vanillax-vllm` session.

## 5. Start and verify

Normal launch after the settings change:

```bash
pi
```

Explicit launch while validating:

```bash
pi --provider vanillax-llama --model qwen3.8-27b --thinking medium
```

Or use the workstation launcher:

```bash
pi-qwen-only
```

Check discovery:

```bash
pi --list-models qwen3.8-27b
```

Expected model row:

```text
provider        model        context  max-out  thinking  images
vanillax-llama  qwen3.8-27b  65.5K    16.4K    yes       yes
```

Inside Pi, `/model` should show `vanillax-llama/qwen3.8-27b`, and the statusline
should show `medium`. `/model` + Ctrl+S and `/thinking` + Ctrl+S are also valid
ways to persist the startup selections.

First tool test from a repository root:

```text
Read package.json and summarize the scripts. Do not guess; use the read tool.
```

You should see a real `read` tool call. Then test a small edit in a disposable
branch and require Pi to run the relevant tests/typecheck.

## 6. Verify reasoning control directly

```bash
pi --model vanillax-llama/qwen3.8-27b --thinking off \
  "Reply with exactly: OFF_OK"

pi --model vanillax-llama/qwen3.8-27b --thinking medium \
  "What is 37*43? Give the answer and a one-line check."
```

If Pi says `off` but the backend still emits a reasoning block, inspect the
request/backend logs before changing model flags.

## 7. Current date/time in Pi

Pi's model is not a clock. Do not trust Qwen to infer today's date from model
training, file timestamps, or session text.

For any current-date/time question, tell Pi to use its built-in bash tool:

```text
Before answering anything date/time-sensitive, run `date` (and `date -u` when
UTC matters). Never infer the current date from model knowledge.
```

Put that rule in `~/.pi/agent/AGENTS.md` if you want it globally. It adds almost
no context and avoids injecting a timestamp into every prompt. Your shell has
the workstation's actual timezone, so `date` is the source of truth for Pi.

Quick test:

```text
What is today's date? Verify with the shell before answering.
```

You should see a bash call to `date` rather than a guessed date.

## 8. Vision / screenshot test

The production backend has the native vision encoder enabled. Attach a
screenshot/image in Pi and ask a concrete question about it.

If text works but images fail:

```bash
kubectl -n vllm logs deploy/vllm-server --tail=200
kubectl -n vllm exec deploy/vllm-server -- nvidia-smi
```

Do not point Pi at ComfyUI for vision; `qwen3.8-27b` itself is multimodal.

## 9. Context discipline

The server ceiling is 262,144 tokens, with two sequences sharing the KV pool.
This does not reserve two full-length sessions. Validate a context ladder
before relying on near-ceiling requests.

For coding agents:

- prefer targeted `read`, `grep`, `find`, and `ls` over dumping whole trees;
- `/compact` before the session becomes mostly historical tool output;
- use `/new` between unrelated tasks;
- avoid giant generated files, lockfiles, logs, or build artifacts;
- parallel subagents contend for the same two-sequence vLLM capacity.

The current backend is optimized for strong single-user interactive latency,
not high-concurrency serving.

## 10. Your installed Pi packages

Your existing package list can stay. Packages/extensions add prompt/tool
surface area, so keep only things you actually use, but there is no backend
migration requirement to remove them.

Useful maintenance:

```bash
pi list
pi update --all
```

For Kubernetes/Talos work, native CLIs through Pi's bash tool (`kubectl`,
`talosctl`, `argocd`, `gh`, `jq`) are usually more context-efficient than
loading a huge MCP catalog.

## 11. Optional global `~/.pi/agent/AGENTS.md`

```markdown
# Environment
- Primary local model: qwen3.8-27b on homelab vLLM FP8, two RTX 3090s, 262K ceiling.
- Free local token volume is not infinite context. Keep reads targeted and
  compact long sessions.
- Prefer actual CLI/tool evidence over guessing.
- For current date/time, run `date` (and `date -u` for UTC); never guess it.

# Kubernetes / homelab
- GitOps only for changes: edit Git and let ArgoCD reconcile.
- kubectl is for inspection unless explicitly told otherwise.
- Follow repository CLAUDE.md / AGENTS.md instructions.
- Secrets go through 1Password + ExternalSecret; never commit them.

# Verification
- Done means verified: run tests, typecheck/lint, or the real command and
  report the result.
```

Pi discovers project context files, so this repo's existing instruction files
remain useful; do not duplicate the whole repository policy globally.

## 12. Backend source of truth

Pi should not carry backend tuning beyond capability metadata. Runtime tuning
lives in:

- `my-apps/ai/vllm/deployment.yaml`
- `my-apps/ai/vllm/README.md`
- `docs/domains/ai-gpu/model-catalog.md`

Declared profile (runtime performance still to be measured):

```text
Official Qwen3.8-27B-FP8
stock vLLM v0.28.0, TP=2
2x RTX 3090
262,144 context ceiling
FP8 E4M3 KV, float16 recurrent state
MTP/speculation off
native vision, one image per request
220 W cap per card
```

If the model ID remains `qwen3.8-27b`, Pi does not need a config change for a
runtime patch or quant replacement unless capabilities/context/reasoning change.
