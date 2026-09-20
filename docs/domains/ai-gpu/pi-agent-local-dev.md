# Pi agent: local Qwen and DeepSeek Flash

**Use `pi-withflash` for automatic routing; use `pi` or `pi-qwen-only` to stay local.**

Pi is the coding agent from [pi.dev](https://pi.dev), not Raspberry Pi. This page
configures a workstation; cluster changes go through Git and ArgoCD.

## Default reasoning and rollout

Local Qwen defaults to **xhigh** with preserved reasoning. This is an
accuracy-first operating choice, not a guarantee of better answers; expect
longer reasoning and more output-budget use. Explicit low, medium and off
remain available on the direct Qwen provider. The model, sampler, 262K context,
32K output allowance and 49,152-token compaction reserve are unchanged.

The companion `mitchross/dotfiles` change sets both Pi's default and the
`pi-qwen-only` alias. After merging both PRs, pull the updated dotfiles source,
preview these two targets with `chezmoi diff`, then apply only those targets:

```bash
chezmoi diff ~/.pi/agent/settings.json ~/.zshrc
chezmoi apply ~/.pi/agent/settings.json ~/.zshrc
source ~/.zshrc
jq '{defaultThinkingLevel, modelThinkingLevels}' ~/.pi/agent/settings.json
type pi-qwen-only
```

Expect the default and local Qwen entry to be `xhigh`, and the local alias to
contain `--thinking xhigh`. Start a fresh Pi session: reloading extensions does
not necessarily change a resumed session's saved thinking level. In an existing
session, explicitly select xhigh. A stale alias or per-model setting can still
send medium and override the server default.

`pi-auto` keeps its medium UI placeholder: it sends no Qwen effort mapping.
Local auto-routed generation therefore inherits the server's xhigh default;
DeepSeek's high/max and the thinking-off classifier stay unchanged. Do not
change the auto provider to xhigh or forward Qwen kwargs into cloud routes.

## The four launchers

| Launcher | Model | Use it for |
|---|---|---|
| `pi-withflash` | `pi-auto` | automatic local/cloud selection |
| `pi` / `pi-qwen-only` | local Qwen, xhigh | nothing may leave the cluster |
| `pi-flash` | DeepSeek Flash | you already know it is hard |
| `pi-direct-openrouter` | DeepSeek Flash, no cluster | the gateway is down |

In `~/.zshrc`:

```bash
# Provider name is load-bearing: scripts/pi/qwen-sampling.ts only fires on
# vanillax-vllm, so a renamed provider silently drops Qwen's sampler.
QWEN=vanillax-vllm/qwen3.8-27b
FLASH=vanillax-openrouter/deepseek-flash
AUTO=vanillax-auto/pi-auto
alias pi-qwen-only="pi --model $QWEN --thinking xhigh --models $QWEN"
alias pi-flash="pi --model $FLASH --thinking high --models $FLASH"
alias pi-withflash="pi --model $AUTO --thinking medium --models $AUTO"
unset QWEN FLASH AUTO
```

Ctrl+P does not pick the backend under `pi-withflash`. Pi always asks for
`pi-auto`; LiteLLM decides behind that alias. To override, use a different
launcher.

A later message can move the same session from Qwen to OpenRouter. Start `/new`
before a cloud-eligible task if the current conversation holds anything that
must not leave the cluster.

## What goes where

| Tier | Model | Effort | Runs on |
|---|---|---|---|
| `SIMPLE`, `MEDIUM` | `qwen3.8-27b-auto` | server default: xhigh | your two RTX 3090s, free |
| `COMPLEX` | `deepseek-flash` | `high` | paid OpenRouter |
| `REASONING` | `deepseek-flash` | `max` | paid OpenRouter |
| classifier failed | `deepseek-flash` | as above | paid OpenRouter |

`SIMPLE` / `MEDIUM` work on local Qwen: greetings, renames, writing tests,
explaining code, inspecting the cluster. `COMPLEX` / `REASONING` work goes to
DeepSeek: debugging, root-cause hunts, architecture.

Classification failures resolve upward. Guessing cheap is the costly miss.

## How it decides

Local Qwen judges each request through the `pi-classifier` route: thinking off,
greedy decoding, a 64-token answer. Greedy is required. Sampled classification
returned `SIMPLE`, `MEDIUM` and `COMPLEX` for one identical input across six
runs, so the same work reached different backends.

`classification_mode: every_request` classifies every request instead of holding
one verdict through a tool loop. LiteLLM **rejects** `stall_escalation_enabled`
alongside `classification_mode: user_turn` or `session_affinity`, because a held
decision hides the tool calls stall detection must watch.

`stall_escalation_enabled` moves a task up a tier when its newest tool call
repeats, or errors, three times in the last six. This is the net for a task Qwen
accepted and then got stuck on. It fires without you noticing.

Include `LITELLM ESCALATE` in a message to force a one-tier bump by hand. It
picks a stronger tier, not a specific model.

The auto router is a **beta** LiteLLM feature. Source of truth is
[`litellm/config.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/litellm/config.yaml).

## Which model answered?

Pi always displays `pi-auto`. It will not tell you.

1. Grafana `/d/pi-routing` — the ratio, the escalation count, the spend
2. Langfuse `langfuse.vanillax.me` — per trace, filter tag `pi`, read `providedModelName`

Pi's cost readout prices every turn as DeepSeek, so local turns look paid when
they cost nothing. Trust the dashboards.

## Safety rails

| Rail | What it does |
|---|---|
| `max_tokens_from_tier_model: false` | keeps Pi's 32K output cap; the default would hand Flash 943K |
| `enable_context_window_escalation: true` | an oversized prompt moves up instead of being truncated |
| `router_settings.fallbacks` | vLLM outage sends **`pi-auto` only** to DeepSeek |

`qwen3.8-27b-auto` is the same vLLM backend as `qwen3.8-27b` under a second
name. Failover is keyed on it alone. LiteLLM fallbacks key on the model name, so
a rule on `qwen3.8-27b` would divert every gateway client — bare `pi`,
`pi-qwen-only`, Open WebUI, Perplexica, Presenton, Hindsight, ninfer, ComfyUI —
to paid OpenRouter during an outage. Local-only callers must fail closed.

## Routing changes need no workstation change

Tiers, effort, escalation and failover for `pi-auto` are server-side. The
launcher only names `vanillax-auto/pi-auto`. Changing its routing needs no
Pi reinstall. Direct-Qwen defaults are different: its workstation settings and
alias send an explicit effort, so the xhigh rollout above needs a chezmoi apply.

## CachyOS workstation inventory

| Item | State |
|---|---|
| OS | CachyOS rolling release, Arch-based |
| Pi | 0.85.1 under `mise`'s Node 24.14.1 |
| Launchers | interactive zsh aliases in `~/.zshrc` |
| Providers | `~/.pi/agent/models.json` |
| Defaults, Ctrl+P scope | `~/.pi/agent/settings.json` |
| Request hook | `~/.pi/agent/extensions/qwen-sampling.ts` |
| Subagents | `@narumitw/pi-subagents` 3.0.1 |

## Keep the sampler current

The hook is a chezmoi **external** with a 168-hour refresh, so a machine can
serve a week-old copy and miss a fix.

```bash
chezmoi --refresh-externals apply ~/.pi/agent/extensions/qwen-sampling.ts
command diff -u ~/.pi/agent/extensions/qwen-sampling.ts \
        ~/src/talos-argocd-proxmox/scripts/pi/qwen-sampling.ts
```

No output from `diff` means current. Running Pi sessions need `/reload`.
The xhigh-default change does not modify the sampler extension itself.

The hook does three things: keeps only the newest image for local Qwen and
`pi-auto`, attaches the Langfuse session id and `pi` tag, and applies Qwen's
sampling to direct `vanillax-vllm` requests. Auto-routed Qwen uses the matching
vLLM server defaults instead.

## Sampling when thinking is off

Pi's thinking toggle changes template kwargs but does not switch Qwen's sampler.
The hook does, for direct Qwen only:

| Thinking | temperature | top_p | presence_penalty | repetition_penalty |
|---|---|---|---|---|
| on | 1.0 | 0.95 | 0.0 | 1.05 |
| off | 0.7 | 0.8 | 1.5 | 1.0 |

Both keep `top_k: 20` and `min_p: 0.0`. Never set `temperature: 0` here — greedy
decoding makes Qwen repeat itself. That rule is for the classifier, not for
generation.

## Images

Local Qwen accepts one image per request. The hook keeps the newest and replaces
older ones with a text marker, so a second screenshot cannot wedge a session.
Comparing two images at once needs an explicit cloud route.

## Subagents

Children inherit the parent's model. Under `pi-withflash` they inherit
`vanillax-auto/pi-auto` and LiteLLM classifies each child's work on its own
merits. Use `pi-flash` for a forced DeepSeek second opinion.

## Direct OpenRouter when the cluster is down

`pi-direct-openrouter` calls DeepSeek Flash with a workstation key, high
reasoning and a 32K output cap. It bypasses LiteLLM and Langfuse entirely and is
billed by OpenRouter.

```bash
alias pi-direct-openrouter='pi --model vanillax-direct-openrouter/~deepseek/deepseek-flash-latest --thinking high --models vanillax-direct-openrouter/~deepseek/deepseek-flash-latest'
```

Provider definition lives in
[`scripts/pi/direct-openrouter.json`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/pi/direct-openrouter.json).
The sampler deliberately leaves these requests untouched.

## Credentials

Provision once, outside chezmoi. Both files are in `.chezmoiignore`.

```bash
(umask 077; op read 'op://homelab-prod/litellm/master_key' > ~/.pi/agent/litellm-api-key)
(umask 077; op read 'op://homelab-prod/open-router/api-key-open-router' > ~/.pi/agent/openrouter-api-key)
```

## Verify

```bash
pi --version
pi --list-models pi-auto
type pi-qwen-only; type pi-flash; type pi-withflash
```

Expect Qwen at roughly 262K context and 32K output, DeepSeek Flash at roughly 1M
context with the deliberate 32K Pi cap, and `pi-auto` at the safe 262K/32K
intersection. All report thinking and image support. The aliases must expand to
the provider/model pairs above, including `--thinking xhigh` for `pi-qwen-only`
and `--models $AUTO` for `pi-withflash`.

Check outgoing request kwargs, not answer length: direct Qwen should send
`enable_thinking=true`, `reasoning_effort=xhigh`, and `preserve_thinking=true`
by default. Repeat with explicit medium, low and off. The
[vLLM acceptance matrix](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md#reasoning-acceptance-checks)
covers tools, images and multi-turn history. A run that exhausts its output
budget is inconclusive; xhigh does not expand the 32K allowance.

## Rollback

To reduce reasoning immediately, select medium on direct Qwen or launch:

```bash
pi --model vanillax-vllm/qwen3.8-27b --thinking medium --models vanillax-vllm/qwen3.8-27b
```

To revert the default permanently, revert the paired GitOps/dotfiles changes
through PRs, apply the restored settings and zshrc, then start a fresh session.
Do not change model weights, sampler or KV precision to roll back effort.

Point `pi-withflash` at `$QWEN` instead of `$AUTO` to roll back automatic routing.
Everything stays local and nothing is billed. Router behaviour reverts through
a PR to `my-apps/ai/litellm/config.yaml`.

## Reference: `~/.pi/agent/models.json`

Three providers, all pointing at the authenticated gateway. The workstation copy
is tracked in `mitchross/dotfiles`; this block is the repo's copy and CI checks
it against `litellm/config.yaml`, so keep the two in step.

```json
{
  "providers": {
    "vanillax-vllm": {
      "baseUrl": "https://litellm.vanillax.me/v1",
      "api": "openai-completions",
      "apiKey": "$LITELLM_API_KEY",
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
    },
    "vanillax-openrouter": {
      "baseUrl": "https://litellm.vanillax.me/v1",
      "api": "openai-completions",
      "apiKey": "$LITELLM_API_KEY",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsUsageInStreaming": true,
        "maxTokensField": "max_tokens",
        "thinkingFormat": "openrouter",
        "requiresReasoningContentOnAssistantMessages": true
      },
      "models": [
        {
          "id": "deepseek-flash",
          "name": "DeepSeek Flash Latest (OpenRouter via LiteLLM, Pi 32K cap)",
          "reasoning": true,
          "thinkingLevelMap": {
            "off": null,
            "minimal": null,
            "low": "low",
            "medium": null,
            "high": "high",
            "xhigh": null,
            "max": "max"
          },
          "input": ["text", "image"],
          "contextWindow": 1048576,
          "maxTokens": 32768,
          "cost": {
            "input": 0.3,
            "output": 1.2,
            "cacheRead": 0.03,
            "cacheWrite": 0
          }
        }
      ]
    },
    "vanillax-auto": {
      "baseUrl": "https://litellm.vanillax.me/v1",
      "api": "openai-completions",
      "apiKey": "$LITELLM_API_KEY",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false,
        "supportsUsageInStreaming": true,
        "maxTokensField": "max_tokens",
        "requiresReasoningContentOnAssistantMessages": true
      },
      "models": [
        {
          "id": "pi-auto",
          "name": "Pi Auto (LiteLLM: local Qwen or OpenRouter DeepSeek Flash)",
          "reasoning": true,
          "thinkingLevelMap": {
            "off": null,
            "minimal": null,
            "low": null,
            "medium": "medium",
            "high": null,
            "xhigh": null,
            "max": null
          },
          "input": ["text", "image"],
          "contextWindow": 262144,
          "maxTokens": 32768,
          "cost": {
            "input": 0.3,
            "output": 1.2,
            "cacheRead": 0.03,
            "cacheWrite": 0
          }
        }
      ]
    }
  }
}
```

Keep every provider and model id stable. The Qwen provider name gates the
sampler hook, and all three model names are referenced by LiteLLM or the
launchers.

## Reference: `~/.pi/agent/settings.json`

Defaults and Ctrl+P scope. CI checks `defaultThinkingLevel` and the per-model
thinking levels, so keep this in step with the workstation copy.

```json
{
  "defaultProvider": "vanillax-vllm",
  "defaultModel": "qwen3.8-27b",
  "defaultThinkingLevel": "xhigh",
  "modelThinkingLevels": {
    "vanillax-vllm/qwen3.8-27b": "xhigh",
    "vanillax-openrouter/deepseek-flash": "high"
  },
  "enabledModels": [
    "vanillax-vllm/qwen3.8-27b"
  ],
  "compaction": {
    "enabled": true,
    "reserveTokens": 49152,
    "keepRecentTokens": 20000
  }
}
```

`compaction.reserveTokens` holds back 49,152 tokens so a long session compacts
rather than overflowing.
