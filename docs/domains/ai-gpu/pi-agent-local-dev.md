# Pi.dev agent with local vLLM and OpenRouter DeepSeek Flash

Current workstation guide, audited 2026-09-16 against Pi **0.85.1**, its installed
provider configuration, and the Git-declared LiteLLM routes. Pi is the coding
agent from [pi.dev](https://pi.dev), not Raspberry Pi. These files configure a
workstation; cluster changes still go through Git and ArgoCD.

Bare `pi` and `pi-qwen-only` use the self-hosted
**`vanillax-vllm/qwen3.8-27b`** path by default. `pi-flash` selects paid,
cloud-hosted **`vanillax-openrouter/deepseek-flash`** only. `pi-withflash` selects the
**`vanillax-auto/pi-auto`** virtual model: LiteLLM automatically keeps
`SIMPLE` / `MEDIUM` work on local Qwen and sends `COMPLEX` / `REASONING` work
to OpenRouter's DeepSeek Flash latest alias, escalating mid-task if Qwen stalls. These three paths enter the authenticated LiteLLM gateway and share
Langfuse session tracing, but only Qwen is served by this cluster's vLLM and
RTX 3090s.

## CachyOS workstation inventory

The 2026-09-16 audit inspected `vanillax-gaming-linux`, not only the GitOps
manifests:

| Item | Current workstation state |
|---|---|
| OS | CachyOS rolling release, Arch-based |
| Pi | 0.85.1 under `mise`'s Node 24.14.1 installation |
| Launchers | interactive zsh aliases in `~/.zshrc`; no Pi user systemd service |
| Providers | `~/.pi/agent/models.json` |
| Defaults and Ctrl+P scope | `~/.pi/agent/settings.json` |
| Workstation instructions | `~/.pi/agent/AGENTS.md` |
| Request hook | `~/.pi/agent/extensions/qwen-sampling.ts` |
| Subagents | `@narumitw/pi-subagents` 3.0.1 |

The CachyOS scan found obsolete Kimi providers/launchers and an older sampler.
That machine still needs the migration below unless separately applied there.
On 2026-09-17 the Mac has all four launchers, the current sampler, and concise
agent instructions. Its installed Pi remains 0.85.1. The chezmoi changes are
tracked separately in [mitchross/dotfiles](https://github.com/mitchross/dotfiles).

## Chezmoi and workstation source of truth

The dotfiles repo manages Pi provider/settings merge scripts, `AGENTS.md`, and
OS-specific zsh launchers. The sampler remains owned by this Talos repo and is
fetched by chezmoi's external-file entry; its cache refresh period is seven days.
Use a forced refresh when deliberately installing a newer sampler.

After the dotfiles PR is merged, inspect and apply on each workstation:

```bash
chezmoi git -- pull --ff-only
chezmoi diff ~/.pi/agent/models.json ~/.pi/agent/settings.json ~/.pi/agent/AGENTS.md ~/.zshrc
chezmoi apply ~/.pi/agent/models.json ~/.pi/agent/settings.json ~/.pi/agent/AGENTS.md ~/.zshrc
chezmoi apply --refresh-externals ~/.pi/agent/extensions/qwen-sampling.ts
```

Expected: local Qwen remains the default and only default Ctrl+P choice;
`pi-flash`, `pi-withflash`, and `pi-direct-openrouter` are separate opt-ins.
Unrelated providers, existing credential references, extra packages, and UI
settings survive. The retired Kimi model and aliases are removed. Check model
listings and alias expansion as described below, then open a fresh terminal
and restart Pi. Review diffs locally: an existing literal credential can appear
in a diff even though the tracked defaults contain only key-file readers.

New installs read `~/.pi/agent/litellm-api-key` for gateway providers and
`~/.pi/agent/openrouter-api-key` for direct OpenRouter. Both are private `0600`
files outside Git and must be provisioned separately on each machine; refresh
local copies after key rotation. Custom provider `/login` is not supported.
The [dotfiles setup guide](https://github.com/mitchross/dotfiles#readme) owns
provisioning steps. Existing environment or `op read` references remain valid
when their prerequisites are available. On the Mac the local key files remove
runtime dependence on 1Password login and, for direct OpenRouter, the cluster.

The shared Pi instructions require brief result-first replies (normally at most
150 words), meaningful 1-2 sentence progress updates, no deliberation transcripts,
and mechanism/gotcha comments of one line, two maximum. Detailed incident
history belongs in docs or Mink. This applies to Qwen and all DeepSeek launchers;
it does not reduce their reasoning effort or change the model's thinking display.

Back up local files before applying. To roll back, restore those backups and
revert the dotfiles change through its PR workflow before the next chezmoi
apply; otherwise the managed configuration will return. Do not delete credentials
or replace unrelated workstation configuration as part of rollback.

## Provider configuration

Back up `~/.pi/agent/models.json`, `settings.json`, and `AGENTS.md` before editing.
Merge these providers into `models.json`; do not overwrite other providers or
credentials. All three are custom `models.json` providers, so `/login` cannot
configure them -- that picker offers only Pi's built-in providers, and custom
provider IDs never appear in the list. Supply the shared LiteLLM key from
1Password (`homelab-prod/litellm/master_key`) through the provider's `apiKey`
field, which resolves `"$VAR"` and `"!command"` values as well as literals:

```text
"apiKey": "$LITELLM_API_KEY"
```

Export that variable from a file outside Git (the workstation uses `~/.ai-keys`,
sourced by `.zshrc`), or read it directly with
`"apiKey": "!op read 'op://homelab-prod/litellm/master_key'"`. Resolution order
is CLI `--api-key`, `auth.json`, environment variable, then the `models.json`
value. A placeholder key fails against this authenticated gateway. Keep
credentials out of Git.

The upstream key was verified on 2026-09-16 as the populated concealed field
`homelab-prod/open-router/api-key-open-router`, which is visible to the
cluster's Connect token. The `litellm` ExternalSecret maps that field to
`OPENROUTER_API_KEY`. Confirm the ExternalSecret becomes Ready before accepting
the LiteLLM rollout. The Deployment also requires that individual Secret key,
so its new container waits if ESO has not added it yet. Never copy the value
into Git or workstation model JSON.

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

DeepSeek Flash is not another model loaded into local vLLM. LiteLLM sends
`deepseek-flash` to `openrouter/~deepseek/deepseek-flash-latest` using the
`OPENROUTER_API_KEY` held by the cluster's `litellm` ExternalSecret. Prompts
leave the homelab, pass through OpenRouter, and may reach the provider
OpenRouter selects for the alias. The alias follows the newest DeepSeek Flash
family member, so its target, limits, providers, and prices can change without
a Git edit.

On 2026-09-16 the public catalog resolved the alias to DeepSeek V4.1 Flash,
with text and image input, a 1,048,576-token model and top-provider context,
and up to 943,718 completion tokens. Individual providers have lower limits.
Pi deliberately caps direct output at 32,768 tokens to control spend and keep
the same practical agent budget as local Qwen. Its
static planning estimate is $0.30/M input, $0.03/M cached input, and $1.20/M
output. That covers the current DeepSeek peak time-window rate, but some
providers charge more; it is not a spending cap or a guaranteed upper bound.
Pi accepts only one price. OpenRouter's billed usage is authoritative;
compare LiteLLM/Langfuse cost records with it before relying on those totals.
[OpenRouter's live model catalog](https://openrouter.ai/api/v1/models),
[current target's provider limits and prices](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints), and
[LiteLLM's OpenRouter provider guide](https://docs.litellm.ai/docs/providers/openrouter)
own the moving upstream contract.

The alias defaults to reasoning enabled at `high` and advertises only `low`,
`high`, and `max` effort. Pi's `thinkingFormat: openrouter` serializes those as
OpenRouter's `reasoning: { effort }` object. Unsupported Pi choices are `null`,
including `off`; do not claim that this alias can disable reasoning. Preserve
reasoning content on replayed assistant messages so tool loops retain the
provider's required conversation shape.

## Automatic Qwen / DeepSeek routing

`pi-auto` is a LiteLLM complexity-router alias, not a third inference backend.
The Git-declared LiteLLM `v1.102.0` policy is:

| Classified tier | Selected gateway model | Reasoning effort | Actual compute |
|---|---|---|---|
| `SIMPLE`, `MEDIUM` | `qwen3.8-27b-auto` | server default | local vLLM on the two RTX 3090s |
| `COMPLEX` | `deepseek-flash` | `high` | paid OpenRouter route |
| `REASONING` | `deepseek-flash` | `max` | paid OpenRouter route |
| unclassifiable ask / classifier failure | `deepseek-flash` | per tier above | paid OpenRouter route |

Qwen owns `SIMPLE` and `MEDIUM`: tests, refactors, code explanation and cluster
inspection all stay on the 3090s. Escalation covers its misses rather than
pre-emptively spending, so the local half of the workload stays real.
Classification failures resolve upward, since guessing cheap is the costly miss.

The classifier uses local Qwen through the `pi-classifier` route, with thinking
disabled, greedy decoding (`temperature: 0`, `top_p: 1`, no penalties) and a
64-token structured response. Qwen's conversational sampling is wrong for a
one-label verdict: at `temperature: 0.7` the same ask classified `SIMPLE`,
`MEDIUM` and `COMPLEX` across six runs, so identical work reached different
backends. Greedy decoding returned the same tier six times out of six. It judges the task's meaning using
LiteLLM's agentic rubric; keyword scoring had classified short incident reports
as SIMPLE. It includes up to four prior user/assistant turns within an 8,000-character
context budget, so approvals such as "yes, do that" can inherit the plan's difficulty.
Classification adds one local inference call per request, with a 30-second
timeout. Errors, invalid output, or timeouts select `deepseek-flash`; the default
classifier circuit breaker temporarily skips classification after a timeout.

`classification_mode: every_request` classifies each request rather than holding
one verdict through a tool loop. LiteLLM **rejects** `stall_escalation_enabled`
alongside `classification_mode: user_turn` or `session_affinity`, because a held
decision hides the tool calls stall detection has to watch. Re-classifying every
request is what buys the mid-task rescue below.

`stall_escalation_enabled` moves a task up one tier when the newest tool call
repeats, or errors, at least three times across the last six calls. This is the
safety net for a task Qwen accepted and then got stuck on: it escalates without
the operator noticing or intervening.

`enable_context_window_escalation: true` moves an oversized request up instead of
letting it be truncated to fit, since a silently truncated prompt is the
hallucination that matters most here.

`router_settings.fallbacks` sends `qwen3.8-27b-auto` failures to `deepseek-flash`,
so a vLLM outage degrades to the paid route instead of failing the request.
`context_window_fallbacks` does the same for a prompt Qwen cannot hold.

`qwen3.8-27b-auto` is the same vLLM backend as `qwen3.8-27b` under a second name,
and exists only so that failover is scoped. LiteLLM fallbacks key on the model
name, so a rule on `qwen3.8-27b` would divert **every** gateway client — bare
`pi`, `pi-qwen-only`, Open WebUI, Perplexica, Presenton, Hindsight, ninfer,
ComfyUI — to paid OpenRouter during a vLLM outage. `pi-qwen-only` exists so that
nothing leaves the cluster, so it must fail closed rather than fail over.

`max_tokens_from_tier_model: false` is required from `v1.102.0`, where it defaults
to true and replaces the caller's output cap with the selected tier model's —
943,718 tokens on Flash, against the 32,768 Pi is told.

This is automatic model selection, not load balancing: one completion goes to one
backend and is never split across Qwen and DeepSeek.

Including `LITELLM ESCALATE` in a message forces a one-tier bump when a result is
unsatisfying. It chooses a stronger tier, not a specific model.

Routing is entirely server-side. The workstation only names
`vanillax-auto/pi-auto`, so tier, effort and escalation changes need no launcher,
`models.json` or chezmoi change.

After this configuration rolls out through ArgoCD, use the Auto Router test UI
with a greeting, a routine rename, and a difficult incident or architecture request.
Expect local tiers for the first two and a DeepSeek tier for the difficult task.
These tests call the local classifier but do not dispatch the selected backend.
Check `routing_decision.cause=llm_classifier`; `default_model_fallback` means
classification failed, rather than the task being judged easy. Revert the classifier
configuration through a PR to restore keyword routing if latency or classification
quality is unacceptable. The source of truth is
[`litellm/config.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/litellm/config.yaml).

The router is a beta LiteLLM feature. Its decision is policy, not a guarantee
of task quality or privacy: any ask classified `COMPLEX` or `REASONING`, plus
the conversation context and tool schema sent with it, leaves the cluster and
incurs OpenRouter charges. Use `pi` or `pi-qwen-only` when content must remain
local, and `pi-flash` when DeepSeek Flash must be forced. Check LiteLLM's
`ComplexityRouter` decision
log or Langfuse `routing_decision` metadata to see the chosen model; Pi continues
to display the `pi-auto` alias. The Pi entry deliberately reports the safe
shared 262,144-token total context and 32,768-token output limits; LiteLLM
advertises 229,376 maximum input tokens so that full output allowance still
fits inside Qwen's window.
[LiteLLM Auto Routing](https://docs.litellm.ai/docs/proxy/auto_routing) owns the
beta behavior and configuration contract.

Pi cannot price two possible upstreams in one static model entry. The
`vanillax-auto/pi-auto` entry therefore uses the same static planning estimate
as direct Flash; local-Qwen turns will look paid in Pi even though their
actual API cost is zero. Use LiteLLM/Langfuse to identify the routed model,
and OpenRouter billed usage to confirm external spend. The auto provider
suppresses a client `reasoning_effort`: Qwen uses the server's fixed medium default and DeepSeek
Flash uses OpenRouter's upstream `high` default. The single exposed Pi level is
descriptive, not an override of either backend.
The auto provider also supplies `reasoning_content` on assistant history,
including an empty string when a prior response had no reasoning, so a later
DeepSeek turn can replay the same tool-call history as the direct route.

Requests pass through LiteLLM for Prometheus metrics and Langfuse AI analytics.
The repo-owned extension attaches Pi's session ID and a `pi` tag to all three
providers, so both branches of `pi-auto` stay grouped in one Langfuse session.
Its Qwen sampling rewrite applies only to direct
`vanillax-vllm/qwen3.8-27b` requests; auto-routed Qwen uses the matching server
default, while LiteLLM drops unsupported optional parameters on heterogeneous
routes.
Explicit caller metadata takes precedence. Local tool execution needs separate
instrumentation; the gateway records model requests and returned tool calls.
Keep all provider and model IDs stable: the Qwen name gates the direct sampler,
and the three model names are referenced by LiteLLM or the workstation launchers.
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
    "vanillax-vllm/qwen3.8-27b": "medium",
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

The **262,144-token window includes input, tool schemas/results, images,
reasoning, and the answer**. `maxTokens: 32768` is the output budget, not an
extra window. Pi compacts when estimated context exceeds the window minus
`reserveTokens`: approximately **212,992 tokens** here. The 49,152 reserve is
our operating recommendation: 32,768 output tokens plus 16,384 for tool growth.
It leaves the full server ceiling available while starting cleanup before a
long tool result exhausts it. This is not an upstream-required value or a
hard protection against arbitrarily large tool output. Compaction settings are
global in Pi. OpenRouter currently advertises a much larger upstream completion
limit, but this provider entry intentionally holds Pi to 32,768 output tokens.
Revisit the reserve and cost guardrails together before increasing that cap.

Compaction summarizes older history and retains a recent tail. It is lossy:
keep task decisions, file paths, verification results, and remaining work in
a concise handoff. Use `/compact` at milestones and `/new` between unrelated
tasks. Avoid whole-repository dumps; search and read relevant sections.
[Pi compaction behavior](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/compaction.md),
[settings and project overrides](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md).

`enabledModels` intentionally keeps bare `pi` local-Qwen-only. The launcher
`--models` flag overrides that Ctrl+P scope for one Pi process without changing
the saved default.

## Workstation launchers and model switching

After `pi-auto` is healthy in LiteLLM, keep these three launchers in `~/.zshrc`:

```bash
# Provider name is load-bearing: scripts/pi/qwen-sampling.ts only fires on
# vanillax-vllm, so a renamed provider silently drops Qwen's sampler.
QWEN=vanillax-vllm/qwen3.8-27b
FLASH=vanillax-openrouter/deepseek-flash
AUTO=vanillax-auto/pi-auto
alias pi-qwen-only="pi --model $QWEN --thinking medium --models $QWEN"
alias pi-flash="pi --model $FLASH --thinking high --models $FLASH"
alias pi-withflash="pi --model $AUTO --thinking medium --models $AUTO"
unset QWEN FLASH AUTO
```

| Launcher | Starts on | Ctrl+P scope | Use it for |
|---|---|---|---|
| `pi` | local Qwen, medium | local Qwen only | normal, private, zero-API-cost work |
| `pi-qwen-only` | local Qwen, medium | local Qwen only | an explicit clean local session |
| `pi-flash` | DeepSeek Flash latest | DeepSeek Flash only | a deliberate paid OpenRouter session |
| `pi-withflash` | `pi-auto` | `pi-auto` only | let LiteLLM select local Qwen or paid DeepSeek Flash for each human turn |

`pi-withflash` does not use Ctrl+P to choose the backend. Pi always requests
`pi-auto`; LiteLLM chooses Qwen or DeepSeek Flash behind that stable alias. Use
the separate `pi-qwen-only` or `pi-flash` launcher to override the policy.
Because a later human turn can move the same session from Qwen to OpenRouter,
start `/new` before a cloud-eligible task when the previous local conversation contains
sensitive content that must not be forwarded.

## Direct OpenRouter during cluster outages

`pi-direct-openrouter` uses paid DeepSeek Flash directly at
`https://openrouter.ai/api/v1`. It bypasses LiteLLM, vLLM, and Langfuse entirely;
these requests will not appear in the homelab dashboards or session traces.
Use OpenRouter activity for billed usage. Bare `pi` remains local-only.
The direct launcher was installed on the Mac on 2026-09-16; the CachyOS
workstation needs the same manual installation if desired.

Prerequisites: Pi 0.85.1, Internet access, and the actual OpenRouter API key
from `homelab-prod/open-router/api-key-open-router` (not the LiteLLM master key).
Back up `~/.pi/agent/models.json`, `settings.json`, `.zshrc`, and the installed
sampler before changing them. Store the key outside Git in
`~/.pi/agent/openrouter-api-key`, readable only by your user. With a signed-in
1Password CLI, provision it without printing its value:

```bash
mkdir -p ~/.pi/agent
(umask 077; op read 'op://homelab-prod/open-router/api-key-open-router' > ~/.pi/agent/openrouter-api-key.new) &&
  test -s ~/.pi/agent/openrouter-api-key.new &&
  mv ~/.pi/agent/openrouter-api-key.new ~/.pi/agent/openrouter-api-key
```

If that command fails, stop and unlock/sign into 1Password; do not replace a
working key with an empty file. Once provisioned, this local copy needs no
cluster or 1Password connection at launch. Refresh it after key rotation.

From the repository root, merge the provider fragment into the existing catalog:

```bash
python3 - <<'PYCODE'
import json
from pathlib import Path
path = Path.home() / ".pi/agent/models.json"
models = json.loads(path.read_text())
fragment = json.loads(Path("scripts/pi/direct-openrouter.json").read_text())
models.setdefault("providers", {}).update(fragment["providers"])
path.write_text(json.dumps(models, indent=2) + "\n")
path.chmod(0o600)
PYCODE
cp scripts/pi/qwen-sampling.ts ~/.pi/agent/extensions/qwen-sampling.ts
```

The [provider fragment](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/pi/direct-openrouter.json)
uses upstream model ID `~deepseek/deepseek-flash-latest`, the same reasoning
compatibility and 32,768 output cap as `pi-flash`, and a local key-file reader.
The sampler leaves this provider untouched, without attaching Langfuse metadata.
Add this alias to `~/.zshrc` and open a fresh terminal:

```bash
alias pi-direct-openrouter='pi --model vanillax-direct-openrouter/~deepseek/deepseek-flash-latest --thinking high --models vanillax-direct-openrouter/~deepseek/deepseek-flash-latest'
```

Run `pi --list-models '~deepseek/deepseek-flash-latest'` and
`type pi-direct-openrouter`. Expect provider `vanillax-direct-openrouter`,
roughly 1M context, 32K output, and the alias above. Start a fresh session with
`pi-direct-openrouter`; this forces direct DeepSeek and does not auto-route.
A missing/invalid key is an authentication error, not a reason to fall back to
the cluster. Prompts, conversation context, and tool schemas go to OpenRouter.

Rollback: remove the alias and `vanillax-direct-openrouter` provider (or restore
the backups), remove the local OpenRouter key if no longer needed, and restart
Pi. No cluster changes are required.
[OpenRouter authentication](https://openrouter.ai/docs/api/reference/authentication)
defines the direct endpoint and upstream credential contract.

## Subagents and DeepSeek second opinions

The installed `@narumitw/pi-subagents` 3.0.1 package makes children inherit the
current session's provider and model. There is no separate per-job model catalog.
Under `pi-withflash`, children inherit `vanillax-auto/pi-auto`, and LiteLLM
classifies their human asks with the same policy. One fanout can therefore
produce a mixture of local and paid requests. Keep auto-routed fanout bounded
and verify its decisions in Langfuse.

Use `pi-flash` for an isolated, forced DeepSeek second opinion. Use
`pi-withflash` when LiteLLM should choose between local Qwen and DeepSeek Flash
automatically. The workstation `AGENTS.md` guidance should describe that
distinction and the cloud-data boundary. Subagents are for independent,
bounded work that benefits from a separate context; they are not a reason to
multiply paid OpenRouter requests.

Two GPU cards do not mean two independent model servers. The live shared pool
holds about 325K tokens; two simultaneous 262K sessions do not fit. Use one
long coding session near the ceiling. A second light request can share the
pool, but parallel agent fanout competes for the same capacity. See the
[measured capacity audit](3090-llm-optimization.md).

## Correct sampling when switching thinking off

Pi's template mapping switches reasoning but does not switch sampling.
The small repo-owned
[Qwen sampler extension](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/pi/qwen-sampling.ts)
uses Pi's `before_provider_request` hook to select the deployment's six
mode-specific sampling values after serialization. It applies only to
`vanillax-vllm/qwen3.8-27b`, leaves messages/tools/template mapping intact, and
sets mode-specific values even if a stale client temperature was selected.

From the repository root, back up any existing copy, then install:

```bash
mkdir -p ~/.pi/agent/extensions
cp scripts/pi/qwen-sampling.ts ~/.pi/agent/extensions/qwen-sampling.ts
```

Restart Pi or use `/reload`. Thinking requests use temperature 1.0, top-p 0.95,
top-k 20, min-p 0, presence penalty 0, repetition penalty **1.05**. Off requests
use 0.7, 0.8, 20, 0, 1.5, **1.0** respectively. The thinking penalty is a local,
community-reported mitigation candidate, not Qwen's official default or a
proven fix. It matches the server and WebUI policy; see the runbook's caveats.
After pulling a sampler update, repeat the copy above and `/reload`: Git/Argo
cannot update an already installed workstation copy. Without this extension,
Pi off still disables reasoning, but needs
another per-request sampler override to match Qwen's recommendation.

On CachyOS, confirm the installed copy matches the repository after copying:

```bash
diff -u ~/.pi/agent/extensions/qwen-sampling.ts scripts/pi/qwen-sampling.ts
```

Expected: no output. The 2026-09-16 audit produced a one-line difference until
the copy step: the installed hook used `1.0`, while the repository uses `1.05`
for thinking and `1.0` for off.
[Pi request hook](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md#before_provider_request),
[canonical server policy and API examples](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/vllm/README.md#explicit-reasoning-and-sampling).

## Vision and browser tools

The local Qwen vLLM server permits **one image in the entire submitted request**
and no video. The repo-owned `qwen-sampling.ts` request hook enforces that budget
for `vanillax-vllm/qwen3.8-27b` and `vanillax-auto/pi-auto`: after Pi serializes
attachments and tool results, it retains the last image and replaces earlier
image parts with explicit text markers. Repeated reads of an attachment also
consume only one image slot. Text, reasoning, tool calls/results, and the saved
session remain intact. Each request is filtered independently, including resumed
sessions and text-only followups after screenshots.

The model sees only the newest image; earlier visual details remain available
only through prior text observations. Re-read an older image to make it current.
For simultaneous image comparison, explicitly select the DeepSeek route and
check its provider limits. Explicit cloud routes are not filtered; auto-routing
always uses Qwen's budget because any new turn can select local inference.
Prefer text/DOM extraction when visual evidence is unnecessary.

Install the updated hook with the copy command above, or refresh the chezmoi
external after this change merges. Run `/reload` in an existing Pi session
before retrying the failed request; new processes load the hook automatically.
No new session or compaction is required with the hook loaded. Verify locally:

```bash
node --test scripts/pi/qwen-sampling.test.mjs
diff -u ~/.pi/agent/extensions/qwen-sampling.ts scripts/pi/qwen-sampling.ts
```

Expected: all tests pass and the installed copy matches. Tests cover accumulated
images, duplicate reads, resumed text followups, unchanged source history, and
cloud-route isolation. To roll back, restore the previous installed hook and
run `/reload`; the one-image server limit then requires manual history control
again. The GPU deployment does not change.

## Recommended agent tools

Start with Pi's built-in file and shell tools. Use the existing LSP integration
for symbol/type diagnostics, a web tool for current documentation, and browser
DevTools when the task needs a logged-in page. Keep installed packages; avoid
adding overlapping tool suites just because the context window is larger.
Inspect `/session` and tool output growth during long work. Small, relevant
outputs preserve room for reasoning and reduce prefill work.

Use a new session for clean validation; resumed sessions may retain their old
model or thinking level. Add `vanillax-openrouter`, then remove the obsolete
Kimi provider only after verifying the new entry; these are custom IDs, so the
rename is manual. The installed Pi version was 0.85.1 during the 2026-09-16
workstation audit. Restart an existing Pi process after changing provider
metadata or launchers.

## Verification and rollback

```bash
pi --version
pi --list-models qwen3.8-27b
pi --list-models deepseek-flash
pi --list-models pi-auto
pi --provider vanillax-vllm --model qwen3.8-27b --thinking medium
pi --provider vanillax-openrouter --model deepseek-flash --thinking high
pi --provider vanillax-auto --model pi-auto --thinking medium
type pi-qwen-only
type pi-flash
type pi-withflash
```

Expected: Qwen reports roughly 262K context and 32K output; DeepSeek Flash
reports roughly 1M context and the intentional 32K Pi output cap; `pi-auto`
reports the safe 262K/32K
intersection. All report thinking and image support. The three aliases must
expand to the provider/model and `--models` scopes shown above. Start normally
with `pi`; use `pi-flash` or `pi-withflash` only when cloud processing and
OpenRouter cost are acceptable. Use `/model` to reload model metadata; direct
Qwen exposes low, medium, xhigh and off, direct DeepSeek Flash exposes low,
high, and max, while `pi-auto` exposes only its fixed medium label.

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

A DeepSeek generation is deliberately absent from the automatic smoke test
because it is paid external work. After rollout, first use LiteLLM's Auto Router test UI
to check simple and complex classification without dispatching the selected
model. When intentionally testing `pi-flash` or a DeepSeek-classified
`pi-withflash` turn, use synthetic content, then verify
`routing_decision.routed_model=deepseek-flash`, the OpenRouter generation, and
recorded cost in Langfuse. Stop if Pi reports an invalid reasoning field and
capture the serialized request before changing the effort mapping.

To roll back workstation changes, restore the backed-up JSON/AGENTS files and
remove the newly installed sampler extension (or restore its previous copy),
then restart Pi. No Kubernetes rollback is needed for workstation files.
Removing the OpenRouter and auto providers plus their two cloud-capable aliases
leaves the local Qwen path intact. Revert the `deepseek-flash` and `pi-auto`
LiteLLM routes through Git for cluster rollback; do not restore obsolete Kimi
credentials or aliases unless a separate change deliberately reintroduces
that provider.
