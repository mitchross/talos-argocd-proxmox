# Pi.dev Agent — local coding against Qwen3.8-27B

> **Current state (2026-09-03):** the sole RTX 3090 serves `qwen3.8-27b`
> through stock llama.cpp `b10752`, Q4_K_XL, q8_0 KV, MTP-2, native vision,
> and a 65,536-token window. The canonical LAN endpoint is
> `https://llama.vanillax.me/v1`.
>
> This document is for **Pi.dev / Pi coding agent**, not Raspberry Pi.

Pi is a workstation client. Nothing in `~/.pi/agent/` deploys to Kubernetes.
The cluster owns the model/runtime; Pi only needs an OpenAI-compatible provider
entry and the model metadata that lets it expose the right reasoning levels,
context window, image input, and token accounting.

## 1. Update Pi itself

```bash
# Pi CLI only
pi update --self

# Or Pi + installed packages/extensions
pi update --all
```

Useful checks:

```bash
pi --version
pi list
```

Pi's current package manager also supports `pi update --models` for refreshed
remote catalogs, but the homelab model below is defined locally in
`models.json`, so that command is not required for this backend.

## 2. `~/.pi/agent/models.json`

Use a dedicated custom provider for the homelab llama.cpp endpoint:

```json
{
  "providers": {
    "vanillax-llama": {
      "baseUrl": "https://llama.vanillax.me/v1",
      "api": "openai-completions",
      "apiKey": "local-no-key-required",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": true,
        "supportsUsageInStreaming": true,
        "maxTokensField": "max_tokens",
        "thinkingFormat": "reasoning_effort"
      },
      "models": [
        {
          "id": "qwen3.8-27b",
          "name": "Qwen3.8 27B (llama.cpp, 1x3090, 65K)",
          "reasoning": true,
          "thinkingLevelMap": {
            "off": "none",
            "minimal": null,
            "low": "low",
            "medium": "medium",
            "high": null,
            "xhigh": "xhigh",
            "max": null
          },
          "input": ["text", "image"],
          "contextWindow": 65536,
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

Why these compatibility settings:

- `openai-completions` matches llama.cpp's `/v1/chat/completions` API.
- `supportsDeveloperRole: false` keeps Pi on a single normal `system` message;
  Qwen3.8's template is stricter than OpenAI's role model and this avoids
  duplicate/developer-system edge cases.
- llama.cpp now accepts top-level OpenAI-style `reasoning_effort`, so the old
  vLLM-era `chat_template_kwargs` workaround is intentionally gone.
- Qwen3.8 accepts `low`, `medium`, and `xhigh`; `none` disables thinking.
  Unsupported Pi levels are explicitly `null`, so Pi hides/clamps them instead
  of inventing values the model template does not understand.
- `input: ["text", "image"]` enables Pi screenshot/image input.
- sampling is deliberately not set in Pi. The production server owns the
  validated Qwen sampling defaults: temp 0.7, top-p 0.8, top-k 20, min-p 0,
  presence penalty 1.5, repeat penalty 1.0.

`models.json` reloads whenever `/model` is opened, so a Pi restart is usually
not needed after editing it.

## 3. `~/.pi/agent/settings.json`

Make the homelab model the default and use **medium** reasoning for normal coding:

```json
{
  "defaultProvider": "vanillax-llama",
  "defaultModel": "qwen3.8-27b",
  "defaultThinkingLevel": "medium",
  "modelThinkingLevels": {
    "vanillax-llama/qwen3.8-27b": "medium"
  }
}
```

You can save the same settings interactively:

1. `/model` → choose `vanillax-llama/qwen3.8-27b` → **Ctrl+S**.
2. `/thinking` → choose `medium` → **Ctrl+S**.

Recommended levels:

| Pi level | Qwen request | Use |
|---|---|---|
| `off` | `reasoning_effort: none` | trivial edits, formatting, lookups |
| `low` | `reasoning_effort: low` | short code changes |
| `medium` | `reasoning_effort: medium` | default coding/debugging/agent work |
| `xhigh` | `reasoning_effort: xhigh` | hard reasoning only |

Do not use `xhigh` as the everyday default. It consumes much more generation
budget and is exactly the overthinking behavior this setup is trying to avoid.

## 4. Start and verify

Normal launch:

```bash
pi
```

Explicit launch while testing the migration:

```bash
pi --provider vanillax-llama --model qwen3.8-27b --thinking medium
```

Or select the provider-qualified model in one argument:

```bash
pi --model vanillax-llama/qwen3.8-27b --thinking medium
```

List what Pi sees:

```bash
pi --list-models qwen3.8-27b
```

Inside a Pi `bash` tool invocation, Pi exposes the selected model and effective
reasoning level:

```bash
printf '%s/%s\n' "$PI_PROVIDER" "$PI_MODEL"
printf 'reasoning=%s\n' "$PI_REASONING_LEVEL"
```

Expected:

```text
vanillax-llama/qwen3.8-27b
reasoning=medium
```

First tool test from the repository root:

```text
Read package.json and summarize the scripts. Do not guess; use the read tool.
```

You should see a real tool call. Then test an edit in a disposable branch and
make Pi run the relevant tests/typecheck rather than merely describing them.

## 5. Vision / screenshot test

The production backend has the BF16 multimodal projector enabled. Attach a
screenshot/image in Pi and ask a concrete question about it. Keep the image
small enough that image tokens do not unnecessarily eat the 65K coding window.

If text works but images fail, check the backend first:

```bash
kubectl -n llama-cpp logs deploy/llama-cpp-server --tail=200
kubectl -n llama-cpp exec deploy/llama-cpp-server -- nvidia-smi
```

Do not point Pi at ComfyUI for vision; `qwen3.8-27b` itself is multimodal.

## 6. Context discipline

The server has one 65,536-token slot. Pi may have unlimited local token
**volume**, but a single request does not have unlimited context.

For coding agents:

- prefer targeted `read`, `grep`, `find`, and `ls` over dumping whole trees;
- `/compact` before the session becomes mostly historical tool output;
- use `/new` between unrelated tasks;
- avoid sending giant generated files, lockfiles, logs, or build artifacts;
- one active llama.cpp sequence slot means parallel subagents contend for the
  same GPU request slot rather than increasing throughput.

The current backend is optimized for strong single-user interactive latency,
not high-concurrency serving.

## 7. Recommended Pi tools/packages

Pi's built-ins (`read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`) are enough
for most repository work. Add packages only where they solve a real workflow:

```bash
# MCP bridge, if you actually need MCP servers from Pi
pi install npm:pi-mcp-adapter

# Then inspect/update packages normally
pi list
pi update --all
```

Keep package count modest on the local model: every extension/tool definition
adds prompt tokens. For Kubernetes/Talos work, native CLIs (`kubectl`,
`talosctl`, `argocd`, `gh`, `jq`) through Pi's shell tool are usually more
context-efficient than loading a giant MCP catalog.

## 8. Global `~/.pi/agent/AGENTS.md` starter

```markdown
# Environment
- Primary local model: qwen3.8-27b on homelab llama.cpp, one RTX 3090, 65K.
- Free local token volume is not infinite context. Keep reads targeted and
  compact long sessions.
- Prefer actual CLI/tool evidence over guessing.

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
remain useful; do not duplicate the whole repository policy into the global
file.

## 9. Backend source of truth

Pi should not carry backend-specific tuning beyond capability metadata. The
cluster owns runtime tuning in:

- `my-apps/ai/llama-cpp/deployment.yaml`
- `my-apps/ai/llama-cpp/README.md`
- `docs/domains/ai-gpu/model-catalog.md`

Current production shape:

```text
Qwen3.8-27B UD-Q4_K_XL
stock llama.cpp b10752
1x RTX 3090
65,536 context
q8_0 target + draft KV
MTP Q4_0, n-max=2
BF16 vision projector
~42-43 tok/s observed interactive decode
~22.7 GiB VRAM under generation
220 W cap
```

If the model ID stays `qwen3.8-27b`, Pi does not need a config change for an
engine patch or quant replacement unless the capabilities/context/reasoning
contract changes.
