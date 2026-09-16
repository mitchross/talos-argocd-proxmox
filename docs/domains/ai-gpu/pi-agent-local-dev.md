# Pi.dev agent with local vLLM and Kimi K3

Current workstation guide, audited 2026-09-16 against Pi **0.85.1**, its installed
provider configuration, and the Git-declared LiteLLM routes. Pi is the coding
agent from [pi.dev](https://pi.dev), not Raspberry Pi. These files configure a
workstation; cluster changes still go through Git and ArgoCD.

Bare `pi` and `pi-qwen-only` use the self-hosted
**`vanillax-vllm/qwen3.8-27b`** path by default. `pik` selects paid, cloud-hosted
**`vanillax-litellm/kimi-k3`** only. `pi-withk3` selects the
**`vanillax-auto/pi-auto`** virtual model: LiteLLM automatically keeps
`SIMPLE` / `MEDIUM` work on local Qwen and sends `COMPLEX` / `REASONING` work
to Kimi K3. All paths enter the authenticated LiteLLM gateway and share
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

The scan found four local drift items. The installed Kimi display name still
says "logged to PostHog" even though LiteLLM now exports to Langfuse; the JSON
below supplies the corrected label. Workstation `AGENTS.md` says
`pi-withk3` runs Kimi, while the audited alias starts on Qwen and merely makes
Kimi available through Ctrl+P. It must be replaced with the auto-router alias
below after the `pi-auto` gateway route is merged and healthy. The installed
sampler also predates the repo's thinking penalty change and still uses
`repetition_penalty=1.0` in both modes. Recopy the extension and reload Pi
before claiming that the workstation uses the repo-declared 1.05 thinking
policy.

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
    "vanillax-litellm": {
      "baseUrl": "https://litellm.vanillax.me/v1",
      "api": "openai-completions",
      "apiKey": "$LITELLM_API_KEY",
      "models": [
        {
          "id": "kimi-k3",
          "name": "Kimi K3 (Moonshot via LiteLLM and Langfuse)",
          "reasoning": true,
          "input": ["text", "image"],
          "contextWindow": 1000000,
          "maxTokens": 131072,
          "cost": {
            "input": 3,
            "output": 15,
            "cacheRead": 0.3,
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
        "maxTokensField": "max_tokens"
      },
      "models": [
        {
          "id": "pi-auto",
          "name": "Pi Auto (LiteLLM: local Qwen or Kimi K3)",
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
            "input": 3,
            "output": 15,
            "cacheRead": 0.3,
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

Kimi K3 is not another model loaded into local vLLM. LiteLLM sends
`kimi-k3` to Moonshot using the `MOONSHOT_API_KEY` held by the cluster's
`litellm` ExternalSecret. Prompts leave the cluster and are billed at the model
metadata above: $3 per million cache-miss input tokens, $0.30 per million
cache-hit input tokens, and $15 per million output tokens. K3 has native vision,
a one-million-token context window, and a Pi-configured 131,072-token output
ceiling.
[Kimi model selection](https://www.kimi.ai/help/kimi-api/api-model-selection)
and [official pricing](https://www.kimi.ai/help/kimi-api/api-pricing) remain the
upstream source of truth.

K3 always thinks; its API supports `low`, `high`, and `max` effort and defaults
to `max` when no effort is supplied. The current workstation entry identifies it
as a reasoning model but does not claim a verified Pi-to-Kimi effort mapping
through LiteLLM. Do not interpret Pi's status-bar level as proof of the upstream
K3 effort, and do not try to switch K3 thinking off. Capture the serialized
request before documenting or depending on an effort override.

## Automatic Qwen / Kimi routing

`pi-auto` is a LiteLLM complexity-router alias, not a third inference backend.
The deployed LiteLLM `v1.101.0` policy is:

| Classified tier | Selected gateway model | Actual compute |
|---|---|---|
| `SIMPLE`, `MEDIUM` | `qwen3.8-27b` | local vLLM on the two RTX 3090s |
| `COMPLEX`, `REASONING` | `kimi-k3` | paid Moonshot API |
| no classifiable human ask / classifier default | `qwen3.8-27b` | local vLLM on the two RTX 3090s |

The built-in heuristic classifier adds no model call. With
`classification_mode: user_turn`, LiteLLM classifies each new human ask and
carries that decision through the assistant/tool continuation requests for that
turn. `session_affinity` remains false, so the next human ask can select the
other backend. This is automatic model selection, not load balancing: one
completion goes to one backend and is never split across Qwen and Kimi.

The router is a beta LiteLLM feature. Its decision is policy, not a guarantee
of task quality or privacy: any ask classified `COMPLEX` or `REASONING`, plus
the conversation context and tool schema sent with it, leaves the cluster and
incurs Kimi charges. Use `pi` or `pi-qwen-only` when content must remain local,
and `pik` when Kimi must be forced. Check LiteLLM's `ComplexityRouter` decision
log or Langfuse `routing_decision` metadata to see the chosen model; Pi continues
to display the `pi-auto` alias. The Pi entry deliberately reports the safe
shared 262,144-token total context and 32,768-token output limits; LiteLLM
advertises 229,376 maximum input tokens so that full output allowance still
fits inside Qwen's window.
[LiteLLM Auto Routing](https://docs.litellm.ai/docs/proxy/auto_routing) owns the
beta behavior and configuration contract.

Pi cannot price two possible upstreams in one static model entry. The
`vanillax-auto/pi-auto` entry therefore shows Kimi's rates as a conservative
upper bound; local-Qwen turns will look paid in Pi even though their actual API
cost is zero. LiteLLM and Langfuse are authoritative for routed model and
actual request cost. The auto provider suppresses a client
`reasoning_effort`: Qwen uses the server's fixed medium default and K3 uses its
upstream default. The single exposed Pi level is descriptive, not an override
of either backend.

Requests pass through LiteLLM for Prometheus metrics and Langfuse AI analytics.
The repo-owned extension attaches Pi's session ID and a `pi` tag to all three
providers, so both branches of `pi-auto` stay grouped in one Langfuse session.
Its Qwen sampling rewrite applies only to direct
`vanillax-vllm/qwen3.8-27b` requests; auto-routed Qwen uses the matching server
default, while LiteLLM drops unsupported sampling parameters before Kimi.
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
    "vanillax-vllm/qwen3.8-27b": "medium"
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
global in Pi. Kimi's 131,072-token maximum is API metadata, not a routine output
target; this Qwen-sized reserve does not guarantee room for an output that large.
Use a project-specific override or compact early before deliberately requesting
a very large Kimi result.

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
K3=vanillax-litellm/kimi-k3
AUTO=vanillax-auto/pi-auto
alias pi-qwen-only="pi --model $QWEN --thinking medium --models $QWEN"
alias pik="pi --model $K3 --models $K3"
alias pi-withk3="pi --model $AUTO --thinking medium --models $AUTO"
unset QWEN K3 AUTO
```

| Launcher | Starts on | Ctrl+P scope | Use it for |
|---|---|---|---|
| `pi` | local Qwen, medium | local Qwen only | normal, private, zero-API-cost work |
| `pi-qwen-only` | local Qwen, medium | local Qwen only | an explicit clean local session |
| `pik` | Kimi K3 | Kimi K3 only | a deliberate paid-cloud K3 session |
| `pi-withk3` | `pi-auto` | `pi-auto` only | let LiteLLM select local Qwen or paid Kimi for each human turn |

`pi-withk3` no longer uses Ctrl+P to choose the backend. Pi always requests
`pi-auto`; LiteLLM chooses Qwen or Kimi behind that stable alias. Use the
separate `pi-qwen-only` or `pik` launcher to override the policy. Because a
later human turn can move the same session from Qwen to Kimi, start `/new`
before a cloud-eligible task when the previous local conversation contains
sensitive content that must not be forwarded.

## Subagents and Kimi second opinions

The installed `@narumitw/pi-subagents` 3.0.1 package makes children inherit the
current session's provider and model. There is no separate per-job model catalog.
Under `pi-withk3`, children inherit `vanillax-auto/pi-auto`, and LiteLLM
classifies their human asks with the same policy. One fanout can therefore
produce a mixture of local and paid requests. Keep auto-routed fanout bounded
and verify its decisions in Langfuse.

Use `pik` for an isolated, forced Kimi second opinion. Use `pi-withk3` when
LiteLLM should choose between local Qwen and Kimi automatically. The workstation
`AGENTS.md` guidance should describe that distinction instead of saying that
`pi-withk3` starts on Kimi. Subagents are for independent, bounded work that
benefits from a separate context; they are not a reason to multiply paid Kimi
requests.

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
and no video. Pi can resend images from earlier turns: one new screenshot plus
an old screenshot can already exceed the limit. This is unrelated to the size
of the text context window. Keep text/DOM extraction as the browser default and
use a screenshot when visual evidence is needed. This is a local vLLM limit,
not a claim about Kimi K3's native vision API.

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
model or thinking level. No provider rename is required for this configuration.
The installed Pi version was 0.85.1 during the 2026-09-16 workstation audit.
Restart an existing Pi process after changing provider metadata or launchers.

## Verification and rollback

```bash
pi --version
pi --list-models qwen3.8-27b
pi --list-models kimi-k3
pi --list-models pi-auto
pi --provider vanillax-vllm --model qwen3.8-27b --thinking medium
pi --provider vanillax-auto --model pi-auto --thinking medium
type pi-qwen-only
type pik
type pi-withk3
```

Expected: Qwen reports roughly 262K context and 32K output; Kimi reports 1M
context and roughly 131K output; `pi-auto` reports the safe 262K/32K
intersection. All report thinking and image support. The three aliases must
expand to the provider/model and `--models` scopes shown above. Start normally
with `pi`; use `pik` or `pi-withk3` only when cloud processing and Kimi's API
cost are acceptable. Use `/model` to reload model metadata; direct Qwen exposes
low, medium, xhigh and off explicitly, while `pi-auto` exposes only its fixed
medium label.

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

A Kimi generation is deliberately absent from the automatic smoke test because
it is paid external work. After rollout, first use LiteLLM's Auto Router test UI
to check simple and complex classification without dispatching the selected
model. When intentionally testing `pik` or a Kimi-classified `pi-withk3` turn,
use synthetic content, then verify `routing_decision.routed_model=kimi-k3` and
the generation in Langfuse. Stop if Pi reports an invalid `reasoning_effort`;
the current guide does not promise K3 effort remapping.

To roll back workstation changes, restore the backed-up JSON/AGENTS files and
remove the newly installed sampler extension (or restore its previous copy),
then restart Pi. No Kubernetes rollback is needed for workstation files.
Removing the Kimi and auto providers plus their two Kimi-capable aliases leaves
the local Qwen path intact. Reverting the `pi-auto` LiteLLM route and restoring
the old manual `pi-withk3` alias returns selection to Ctrl+P. For server-policy
rollback, revert the reasoning-policy commit through Git.
