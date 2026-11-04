---
name: hermes-model-routing
description: Route Hermes subagents and helper calls to cheaper models.
version: 0.1.0
author: Hermes
metadata:
  hermes:
    tags: [Hermes, Delegation, Model Routing, Fallback, GitOps]
---

# Hermes Model Routing

Sets up per-subagent model routes (the official `advanced-delegation` plugin), helper-task (auxiliary) models, and a provider fallback chain for the Git-managed Hermes pod. Everything ships as one PR to talos-argocd-proxmox. It does not change the main chat model, and it never edits the live `config.yaml`, because the next pod start overwrites it.

## When to Use
- "Set up the model routing / delegation from that video."
- "Use my Codex, Claude, Qwen, DeepSeek and local models."
- "Stop burning my Claude limits." / "Fall back to Codex when Claude rate-limits."
- "Move compression, titles or Kanban jobs to a cheap model."

## Prerequisites
- Hermes 0.22.5 or newer (`/opt/hermes/bin/hermes --version`). The plugin refuses older cores.
- Repo rules from the `homelab-gitops-change-prs` skill: worktree, feature branch, PR, never merge.
- Provider logins already on the volume: `hermes auth list` shows `anthropic`, `openai-codex`, `copilot`, `custom:litellm`.

## How to Run
Invoke every command through the `terminal` tool. Edit the worktree copy of `my-apps/development/hermes/config/config.yaml` with `patch`. Validate with `scripts/validate_routes.py`.

## Quick Reference
- Model ids per provider: `/opt/data/provider_models_cache.json`. LiteLLM list: `GET http://litellm-service.litellm.svc.cluster.local:4000/v1/models`.
- Install the plugin: `hermes plugins install advanced-delegation`. It lands in `/opt/data/plugins/advanced-delegation`. Pin a commit with `--ref <40-char-sha>`. Run non-interactively with `--enable --yes-deps`.
- Route block: `delegation.backend: model_map`, `delegation.backends.model_map.{default, options[]}`. Each option has `name`, `description`, `provider`, `model`, optional `reasoning_effort`, `service_tier` and `fallback_providers`.
- Chat fallback: top-level `fallback_providers: [{provider, model}]` plus `fallback.min_switch_reset_seconds`.
- Helper tasks: `auxiliary.<task>.{provider, model}`. Tasks include `title_generation`, `skills_hub`, `mcp`, `triage_specifier`, `kanban_decomposer`, `compression`, `approval`, `curator`. Defaults are in `/opt/hermes/hermes_cli/config_defaults.py`.
- Docs: `/docs/plugins/advanced-delegation` and `/docs/user-guide/features/fallback-providers`.

## Procedure
1. Inventory the models. Read the provider cache and the LiteLLM model list. Check in the LiteLLM config which models are local (vLLM) and which go through OpenRouter: `deepseek-flash` is cloud, not local.
2. Install the plugin on the volume so validation can import it: `hermes plugins install advanced-delegation`. It stays inert until the restart.
3. Write the routes in the worktree config. Keep the descriptions to one line, because they are the only thing the agent reads when it picks a route. The current set:
   - `local`: `litellm` / `qwen3.8-flash-next` (Strata only, no cloud fallback)
   - `fast`: `litellm` / `deepseek-flash`
   - `balanced`: `anthropic` / `claude-sonnet-5-5` (this is the default)
   - `codex`: `openai-codex` / `gpt-6.1-sol`
   - `deep`: `anthropic` / `claude-opus-5-5` at `reasoning_effort: high`
   Keep `delegation.provider/model` too, so switching `backend: default` is the rollback.
4. Add the chat fallback chain: `openai-codex/gpt-6.1-sol`, then `litellm/deepseek-flash`, with `min_switch_reset_seconds: 120`. Give the Claude routes a `fallback_providers` entry pointing at Codex.
5. Move the cheap helper tasks to `litellm/deepseek-flash`: titles, `skills_hub`, `mcp`, `triage_specifier`, `kanban_decomposer`. Kanban's task decomposer is the biggest token user. Keep `compression` and `approval` on the main model.
6. Add `advanced-delegation` to `plugins.enabled` and to the plugin loop in `scripts/seed.sh`. Update the model-policy line in the Hermes `CLAUDE.md`.
7. Validate: run `scripts/validate_routes.py <worktree config.yaml>`. Every route and fallback must print OK.
8. Commit, push and open the PR. Cite both docs pages in the body. Tell the user to merge between jobs, then open a NEW chat.

## Pitfalls
- A missing plugin fails closed. If `backend: model_map` is set while the plugin directory is missing, every `delegate_task` call is refused ("No subagent was started"). Hermes itself still runs.
- `seed.sh` runs under `set -eu`, and its plugin install has no `|| echo` fallback. If GitHub is unreachable on a fresh volume, the init container fails and Hermes never starts.
- Codex credentials can't be reconstructed. `openai-codex` lives only in `$HERMES_HOME/auth.json` and has no env-var path. On a fresh volume the `codex` route and the Codex fallback fail until someone runs `hermes auth add openai-codex`.
- One-shot runs (`hermes chat -q`) cap delegation at 2 subagents (`delegation.oneshot_max_children`). Test the routes two at a time. Each result names its route in `route.label` (there is no `option` field), plus `provider` and `model`.
- Routes are built at session start. Chats already open keep the old schema, and the merge restarts the pod and kills running agents.
- Routing doesn't save main-chat quota: the main chat stays on Opus. Say so when the user expects "no more limits". The fallback chain is what actually stretches them.
- Users ask "why can't it auto-select?" It does: the parent picks a route for each subagent. `default` only applies to tasks that pick none.
- `api_key:` on a route is stored in plain text. Use `provider:` so credentials stay in env or `auth.json`.
- The validator checks credentials against whatever `HERMES_HOME` is exported. Run it with `HERMES_HOME=/opt/data` for the live check, or with an empty scratch home to see what breaks on a fresh volume. With an empty home, the `litellm` routes show "Unknown provider" because that home has no `providers:` block, and `openai-codex` shows "no Codex OAuth token". Subagents can leave `HERMES_HOME` pointing at a scratch dir in the shared terminal, so check `echo $HERMES_HOME` before you trust a failure.
- To see the real model split, don't use LiteLLM metrics alone: every in-cluster app shares one LiteLLM key with no alias, and Anthropic and Codex calls bypass LiteLLM. Hermes's own records are complete: `hermes insights --days N`, the dashboard Analytics tab, `state.db` table `session_model_usage` (model, billing_provider, task = '' for the main loop, joined to `sessions.source` for desktop/kanban/subagent/cron), and the Grafana board `/d/hermes-ai-split` fed by the `usage-exporter` sidecar. Relay shared metrics only upload to Nous; the catalog `hermes_otel` plugin is the OTLP route but sends full prompts unless `content_capture: off`.
- For a source video, transcribe it with the `video-transcribe` skill. Hand the user a timestamped summary, not the full verbatim transcript.

## Verification
Invoke through the `terminal` tool: `HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python scripts/validate_routes.py <worktree>/my-apps/development/hermes/config/config.yaml`. It should print OK for every route and fallback. After the merge and restart, run one `delegate_task` per route and check that each result's `route` field names the expected provider and model.
