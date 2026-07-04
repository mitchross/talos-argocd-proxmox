# Pi Agent — Claude-Code-Grade Local Dev on the Dual-3090 Backend

> Goal: a fully local coding agent ([pi](https://github.com/badlogic/pi-mono),
> `packages/coding-agent`) that mimics the Claude Code workflow — tools, repo
> context, skills, research — backed by the cluster's tuned vLLM endpoint
> (`qwen3.6-27b`, TP=2 across both 3090s, 262K context, vision, tool calling).
> Free unlimited *volume*; keep paid frontier APIs for the hardest 10%.
>
> Stack targets: Kubernetes/Talos GitOps (this repo), JavaScript/Node/
> TypeScript, Python, React Native, Temporal.io.
>
> Last updated: 2026-07-04.

## Architecture

```
pi (workstation TUI)
  └── https://vllm.vanillax.me/v1          (internal gateway route, LAN only)
        └── vLLM TP=2 · qwen3.6-27b · 262K ctx · vision · qwen3_coder tool parser
              └── 2× RTX 3090 @ 290W cap (my-apps/ai/gpu-power-limit/)
```

Everything agent-side lives on the workstation (`~/.pi/agent/`); nothing here
deploys to the cluster. The backend is already agent-tuned **server-side** —
don't fight these from the client:

| Server flag (see `my-apps/ai/vllm/deployment.yaml`) | Why pi cares |
|---|---|
| `--served-model-name qwen3.6-27b` | the `id` pi must send |
| `--max-model-len 262144` | matches `contextWindow` below |
| `--max-num-seqs 2` | pi + ONE other consumer concurrently; a third request queues |
| `--enable-auto-tool-choice` + `--tool-call-parser qwen3_coder` | pi's tool calls parse natively |
| `--reasoning-parser qwen3` + thinking off by default | pi gets clean content; thinking is opt-in per request |
| `--override-generation-config` (temp 0.7 / top_p 0.8 / top_k 20 / presence 1.5) | correct Qwen agent sampling — leave pi's sampling unset |
| `--limit-mm-per-prompt {"image": 16}` | screenshot budget per prompt (pi resends the whole convo — see gotchas) |
| HTTPRoute `timeouts: 30m` | long generations won't be cut by the gateway |

## 1. Point pi at the cluster — `~/.pi/agent/models.json`

```json
{
  "providers": {
    "homelab": {
      "baseUrl": "https://vllm.vanillax.me/v1",
      "api": "openai-completions",
      "apiKey": "none",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false,
        "thinkingFormat": "chat-template",
        "chatTemplateKwargs": { "enable_thinking": { "$var": "thinking.enabled" } }
      },
      "models": [
        {
          "id": "qwen3.6-27b",
          "name": "Qwen3.6-27B (homelab 2x3090)",
          "reasoning": true,
          "input": ["text", "image"],
          "contextWindow": 262144,
          "maxTokens": 32768,
          "cost": { "input": 0, "output": 0 }
        }
      ]
    }
  }
}
```

- `enable_thinking` is Qwen's chat-template kwarg; the server defaults it off
  (`--default-chat-template-kwargs`), and this mapping lets pi's thinking
  toggle (Shift+Tab) turn it on per request. If thinking doesn't engage,
  try `"thinkingFormat": "qwen"` (pi ships a qwen preset) and re-test —
  `models.json` hot-reloads on `/model`, no restart needed.
- `input: ["text","image"]` enables pi's screenshot flow (the 27B is
  multimodal).
- Select with `/model` or `pi --model qwen3.6-27b`. Verify tools work:
  `pi "read package.json and summarize the scripts"` — you should see a
  `read` tool call, not a hallucinated answer.

## 2. Claude Code → pi capability map

| Claude Code | pi equivalent | Notes |
|---|---|---|
| `CLAUDE.md` | `AGENTS.md` (global `~/.pi/agent/`, plus per-repo, concatenated up the dir tree) | this repo already ships `CLAUDE.md`s — symlink or copy: `ln -s CLAUDE.md AGENTS.md` |
| Skills | Skills — **same Agent Skills standard** | `~/.pi/agent/skills/` or `.pi/skills/`; invoke `/skill:name` |
| Slash commands | Prompt templates in `~/.pi/agent/prompts/` / `.pi/prompts/` | plain markdown, `/name` expands |
| MCP servers | **`pi install npm:pi-mcp-adapter`** (not in core — see §4a) | token-efficient proxy: ONE `mcp` tool (~200 tokens) instead of hundreds of tool defs |
| Subagents / Task | **`pi-subagents` package** (not in core) | parallel isolated agents — but see the `max-num-seqs 2` warning in §4a |
| Plan mode | **`pi-plan` package** — read-only planning + approval-based execution | the Claude Code plan-mode equivalent |
| Session resume / compact | `pi -c`, `pi -r`, `/compact`, `/fork`, `/tree` | sessions in `~/.pi/agent/sessions/` |
| Permission modes | `trust.json` + tool allow flags (`--tools`, `--exclude-tools`) | |
| Custom tools/hooks | TypeScript extensions in `~/.pi/agent/extensions/` | can replace built-ins, add checkpointing |

The design difference: Claude Code ships everything integrated; pi keeps the
**core minimal** and everything else — MCP, subagents, memory, planning — is
opt-in via the [pi.dev/packages](https://pi.dev/packages) ecosystem
(`pi install npm:<pkg>` / `pi install git:<repo>`; `pi list` / `pi update
--all` to manage). For a batteries-included start, **LazyPi** is a curated
one-command bundle (60+ community skills, MCP support, subagents, persistent
memory, planning mode) that installs into `~/.pi/agent/` and can be removed
piecemeal. On this stack the shell still covers most needs — every system we
run (Kubernetes, ArgoCD, Temporal, git, pnpm, uv) has a first-class CLI — so
treat packages as additive, not required.

## 3. Global `~/.pi/agent/AGENTS.md` starter

```markdown
# Environment
- Local model (qwen3.6-27b on homelab vLLM). Free tokens, 262K window, but
  PREFILL IS EXPENSIVE: keep context lean, prefer targeted reads over
  dumping whole trees. Compact or /new between unrelated tasks.
- You have bash. Prefer CLIs over guessing: kubectl, talosctl, argocd,
  temporal, gh, jq, curl.

# Kubernetes / homelab (talos-argocd-proxmox repo)
- GitOps ONLY: never kubectl apply/edit/delete to fix state — change git,
  let ArgoCD sync. kubectl is for READING (get/describe/logs/events).
- Directory = ArgoCD Application. Every YAML must be listed in its
  kustomization.yaml. Follow the repo's CLAUDE.md files — they are law.
- Secrets: 1Password + ExternalSecret. Never write a secret into git.

# TypeScript / Node
- pnpm. Strict TS. No `any` without a comment. Vitest for tests.
- Match existing lint/format config; run `pnpm tsc --noEmit && pnpm lint`
  before declaring done.

# Python
- uv for envs/deps. ruff for lint+format. pytest. Type hints on public
  functions.

# React Native
- Expo unless the repo says bare. Never edit ios/android generated dirs
  by hand in managed projects. After native dep changes: rebuild dev
  client, not just metro reload.

# Temporal
- Workflow code MUST be deterministic: no Date.now/Math.random/direct IO
  in workflows — use activities, side effects, or workflow APIs.
- Versioning: use patching/versioned workflows for changes to in-flight
  workflow definitions. Test with @temporalio/testing time-skipping.

# Verification discipline
- Done = ran it. Tests, typecheck, or a real invocation — paste the output.
```

Per-repo `AGENTS.md` adds specifics (commands, layout). For *this* repo the
nested `CLAUDE.md` files already contain the right content — reuse them.

## 4. Skills for the stack

Skills are directories with a `SKILL.md` (Agent Skills standard — same format
Claude Code uses, so they're portable both ways). Suggested starter set under
`~/.pi/agent/skills/`:

### `k8s-debug/SKILL.md`

```markdown
---
name: k8s-debug
description: Read-only triage of the homelab Kubernetes cluster (Talos +
  ArgoCD). Use when asked to investigate pod failures, sync errors, PVC
  issues, or GPU workload state.
---

READ-ONLY. Diagnose with kubectl get/describe/logs/events and argocd CLI;
propose fixes as git diffs against talos-argocd-proxmox, never kubectl
apply/edit.

Triage order:
1. `kubectl get applications -n argocd | grep -v 'Synced.*Healthy'`
2. `kubectl -n <ns> get pods,pvc,events --sort-by=.lastTimestamp | tail -30`
3. `kubectl -n <ns> logs <pod> --previous --tail=100` for crash loops
4. GPU apps (vllm/llama-cpp/comfyui) are mutually-exclusive whole-card
   scale-swaps — "Pending + 0/2 nodes available (gpu)" usually means another
   GPU app holds the cards, NOT a broken scheduler.
5. Backups: `kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore,snapshot`
```

### `research/SKILL.md`

```markdown
---
name: research
description: Web research via the homelab's local search stack (SearXNG +
  Perplexica). Use for library docs, error messages, release notes, or any
  "look this up" request.
---

Two tiers, both local/private:

1. Quick lookups — SearXNG JSON:
   `curl -s 'https://search.vanillax.me/search?q=QUERY&format=json' | jq '.results[:5] | .[] | {title, url, content}'`
   (needs `format: json` enabled in SearXNG settings — check once)
2. Synthesized answers with citations — Perplexica API:
   `curl -s https://perplexica.vanillax.me/api/search -H 'Content-Type: application/json' -d '{"query":"QUERY","focusMode":"webSearch","optimizationMode":"balanced"}'`
   (verify the request schema against the deployed Perplexica version once,
   then pin the working curl here)

Fetch promising URLs with `curl -sL` and read the content — don't answer
from snippets alone. Cite URLs in the final answer.
```

### `temporal-dev/SKILL.md`

```markdown
---
name: temporal-dev
description: Inspect and debug Temporal workflows on the homelab cluster
  (worker versioning, stuck workflows, task queue backlogs).
---

UI: https://temporal.vanillax.me
CLI: port-forward the frontend first (verify svc name in the temporal ns):
  `kubectl -n temporal port-forward svc/temporal-frontend 7233:7233 &`
  `temporal --address localhost:7233 workflow list --query 'ExecutionStatus="Running"'`
Useful: `temporal workflow show -w <id>` (event history — find the stuck
activity), `temporal task-queue describe -t <queue>` (are workers polling?).
KEDA scales workers off task-queue depth — a backlog with 0 workers means
check the ScaledObject before blaming the worker image.
```

JS/TS, Python, and React Native generally don't need skills — they need the
conventions in `AGENTS.md` plus pi's built-in `read/edit/bash/grep`: the model
runs `pnpm test`, `tsc`, `ruff`, `pytest`, `npx expo` like any other command.
Add a skill only when a workflow has non-obvious steps worth encoding (e.g.
a `release/` skill for your publishing checklist).

## 4a. Extensions: MCP, subagents, plan mode

Core pi has none of these; the package ecosystem does. What's worth installing
here, and why the choices interact with the *local* backend:

```bash
pi install npm:pi-mcp-adapter   # MCP servers (restart pi after)
pi install npm:pi-plan          # read-only plan mode + approve-to-execute
pi install npm:pi-subagents     # parallel isolated subagents (read warning below)
```

**MCP via `pi-mcp-adapter`** — config lives in `~/.pi/agent/mcp.json` (global)
or `.mcp.json` / `.pi/mcp.json` (per-project), Claude-compatible format:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    },
    "some-http-server": {
      "url": "http://localhost:3845/mcp",
      "headers": { "Authorization": "Bearer ${API_KEY}" }
    }
  }
}
```

Manage with `/mcp` (interactive panel), `/mcp setup`, `/mcp reconnect <server>`.

Why this adapter is the right one for a **local** model specifically: it
exposes **one `mcp` proxy tool (~200 tokens) instead of hundreds of tool
definitions**, with on-demand tool search and lazy server lifecycle (connect
on first call, disconnect after idle). On the 27B, prefill is the tax (gotcha
#1) and every tool definition is resent each turn — a fat MCP toolset would
bloat every single request. Keep proxy mode as the default; promote only your
hottest 2–3 tools to `"directTools"` if the model fumbles the proxy calls.

Useful servers for this stack: `chrome-devtools-mcp` (React/React-Native web
debugging — the one capability plain bash can't fake), a Kubernetes MCP server
if you want structured cluster reads instead of the `k8s-debug` skill's
kubectl calls, GitHub MCP for PR/issue flows. Skip MCP wrappers for things
with good CLIs (temporal, argocd) — the CLI costs zero context.

**Subagents (`pi-subagents`) — mind the backend.** Parallel subagents each
open their own request against vLLM, and `--max-num-seqs 2` means a fan-out
of 3+ queues (and each queued request still pays full prefill when it lands).
Use subagents for *sequential isolation* (fresh context per task) rather than
wide parallel fan-outs — or raise `--max-num-seqs` in
`my-apps/ai/vllm/deployment.yaml` first and accept the KV-pool split at
long context.

**Plan mode (`pi-plan`)** — read-only propose→approve→execute. Recommended
default for anything touching this repo, since a wrong `kubectl` habit here
becomes a cluster incident; it pairs with the `k8s-debug` skill's
"diagnose read-only, fix via git" rule.

## 5. Research & RAG strategy

- **Code understanding: agentic retrieval beats embedding RAG.** With 262K of
  context and grep/read tools, pi navigates repos the way Claude Code does —
  search, open, follow imports. Don't build a vector index of your code; it
  goes stale and retrieves worse than the model's own targeted greps.
- **Web research:** the `research` skill above (SearXNG for hits, Perplexica
  for synthesized+cited answers). This is the local replacement for Claude
  Code's WebSearch/WebFetch.
- **Long-document Q&A:** just read the file(s) into context — that's what the
  262K window is for. But mind the prefill bill (below); for a 500-page spec,
  Perplexica-style retrieval first, full read second.
- **Offline references:** the Kiwix instance (wired into open-webui's mcpo)
  is also plain HTTP — add a curl line to the research skill if devdocs/wiki
  bundles are loaded.

## 6. Operational gotchas (the ones that will bite)

1. **Prefill is the tax, not decode.** pi resends the whole conversation
   every turn; at 100K+ context each turn pays a multi-second-to-minutes
   prefill even with chunked prefill enabled. Discipline: `/compact` at
   milestones, `/new` per task, don't paste what the model can `read`.
2. **Concurrency budget is 2.** `max-num-seqs 2` at 262K. pi + Open WebUI is
   fine; pi + Perplexica deep-research + Karakeep tagging burst = queuing.
   One heavy agent at a time.
3. **Screenshots accumulate.** The 16-image cap exists because pi resends
   convo history (see deployment.yaml comment). If a session wedges with
   "At most N image(s) per prompt", `/compact` (drops old images) or `/new`.
4. **Internal route only.** `vllm.vanillax.me` resolves via the internal
   gateway — works on LAN/VPN, not from outside. Don't expose the /v1
   endpoint externally; it's unauthenticated.
5. **Don't override sampling client-side.** Server defaults are the tuned
   Qwen-agent profile (incl. presence_penalty 1.5, which stops tool-call
   loops). If pi settings expose temperature etc., leave them unset.
6. **After GPU scale-swaps, pi errors are expected.** If vLLM is scaled to 0
   (image-gen session on the cards), pi gets connection errors — that's the
   whole-card topology, not a bug. Scale vLLM back to 1 in git.
7. **Free upgrade pending:** swapping the vLLM checkpoint to AutoRound INT4 +
   MTP n=3 (club-3090's default dual recipe) is specifically a *code-decode*
   win (149 → ~264 TPS on code) — pi is the workload that benefits most.
   Tracked in `3090-llm-optimization.md`.

## 7. Verify checklist

- [ ] `pi --list-models` shows `qwen3.6-27b`; `/model` selects it
- [ ] `pi "run 'ls' and tell me what you see"` → real `bash` tool call
- [ ] Tool-call loop test: "read X, edit Y, run tests" chain completes
      without the model narrating instead of calling tools
- [ ] Shift+Tab thinking toggle produces `<think>`-backed answers (server
      splits it into `reasoning_content`; pi should render it as thinking)
- [ ] Paste a screenshot → model describes it (vision path through gateway)
- [ ] `/skill:research quick lookup test` hits SearXNG and returns JSON
- [ ] (if pi-mcp-adapter installed) `/mcp` lists servers; a proxy
      `mcp({ search: ... })` call resolves a tool
- [ ] Long session: `/compact` works and the next turn's prefill drops

## Related docs

- [`model-catalog.md`](model-catalog.md) — what `qwen3.6-27b` is, app→backend wiring
- [`3090-llm-optimization.md`](3090-llm-optimization.md) — engine/KV analysis, power profile, wind-down roadmap
- [pi docs — models](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/models.md) · [pi coding agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) · [pi.dev/packages](https://pi.dev/packages) · [pi-mcp-adapter](https://github.com/nicobailon/pi-mcp-adapter)
