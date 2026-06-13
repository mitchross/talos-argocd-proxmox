# OpenCode vLLM Setup Design

## Goal

Expand `my-apps/ai/vllm/README.md` into a practical runbook for installing
OpenCode on macOS or Linux and connecting it to this cluster's vLLM endpoint.

## Scope

The README will:

- Replace stale scaffold and first-deploy wording with the current deployed
  configuration.
- Document OpenCode installation using the official installer, with Homebrew
  and npm as supported alternatives where applicable.
- Put the user-wide configuration at
  `~/.config/opencode/opencode.json` on both macOS and Linux.
- Configure an `@ai-sdk/openai-compatible` provider named `vllm`.
- Use `https://vllm.vanillax.me/v1` as the base URL.
- Use `qwen3.6-27b` as the server model ID and `vllm/qwen3.6-27b` as the
  OpenCode model selector.
- Declare the 262,144-token context limit and a conservative output limit.
- Explain that the endpoint is reachable only from the trusted local network
  or an equivalent private-network path and currently requires no API key.
- Include endpoint checks, OpenCode startup and model selection, upgrades,
  uninstall guidance, and focused troubleshooting.

No OpenCode configuration file will be committed for direct deployment. The
README will contain a copy-paste global configuration because the target path
is in each user's home directory.

## Configuration Shape

The documented global config will use JSONC-compatible syntax but remain valid
JSON:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "vllm/qwen3.6-27b",
  "provider": {
    "vllm": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Homelab vLLM",
      "options": {
        "baseURL": "https://vllm.vanillax.me/v1"
      },
      "models": {
        "qwen3.6-27b": {
          "name": "Qwen3.6 27B (vLLM)",
          "limit": {
            "context": 262144,
            "output": 32768
          }
        }
      }
    }
  }
}
```

The model key must match the ID returned by `GET /v1/models`. The README will
tell operators to check that response before troubleshooting OpenCode.

## Verification

Documentation verification will consist of:

- Parsing the embedded configuration as JSON after extracting it from the
  README.
- Checking repository links and commands for the exact service hostname and
  model ID.
- Reviewing the rendered diff for stale `latest`, `replicas: 0`, and
  first-deploy claims.

The guide will cite the official OpenCode documentation for installation,
configuration locations, and custom OpenAI-compatible providers.
