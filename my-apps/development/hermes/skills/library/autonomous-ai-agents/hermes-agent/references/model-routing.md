# Model routing: subagent routes and auxiliary models

Three layers decide which model runs what:

| Layer | Config | Picks |
|---|---|---|
| Main model | `model.provider` / `model.default` | the chat itself |
| Auxiliary | `auxiliary.<task>.provider/model` (`title_generation`, `skills_hub`, `mcp`, `compression`, `approval`, `triage_specifier`, `kanban_decomposer`, `curator`, ...) | small internal helper calls; `auto` = main model |
| Delegation | `delegation.backend`: `default`, `model_map`, `profile_routes` | the model or profile for each `delegate_task` child |
| Fallback | top-level `fallback_providers:` list (+ per-route `fallback_providers`) | what the chat or a route moves to when its provider rate-limits or errors |

`model_map` and `profile_routes` come from the official `advanced-delegation` plugin (needs Hermes >= 0.22.5). Only one backend is active at a time. With a plugin backend active, `delegation.model/provider` are ignored. Docs: `/docs/plugins/advanced-delegation`.

## Procedure
1. **Inventory every model the user has before you design routes.** Don't copy the routes from a tutorial. The user expects their own Claude, Codex, local and cheap models to be used.
   - `hermes auth list`: authed providers (e.g. `anthropic`, `openai-codex`, `copilot`, `custom:<name>`).
   - `$HERMES_HOME/provider_models_cache.json`: model ids per provider (and `$HERMES_HOME/.codex/models_cache.json` for Codex).
   - `config.yaml` `providers:`: named custom endpoints (a LiteLLM proxy). Check what each LiteLLM model really is in the LiteLLM config, because a model there may be a cloud model (OpenRouter), not a local one.
2. Install the plugin: `hermes plugins install advanced-delegation`. It installs disabled. Enable it with `plugins.enabled`. `hermes delegation config` and `/delegation` exist only after the plugin loads, which happens on a gateway restart.
3. Write routes under `delegation.backends.model_map.options` (`name`, `description`, `provider` or `base_url`, `model`, optional `reasoning_effort`, `service_tier`). Set `default:` to the current helper model so untagged tasks behave as before. Use a named custom provider (`provider: litellm`) instead of `api_key`, which would store the key in plain text in `config.yaml`. The agent reads only the name and description, so the description has to say when to pick the route (cost, speed, privacy).
4. Validate each route with the plugin's own validator before the restart:
   ```bash
   cd /opt/hermes && .venv/bin/python - <<'EOF'
   import sys, importlib.util, ruamel.yaml as ry; sys.path.insert(0, '/opt/hermes')
   s = importlib.util.spec_from_file_location('s', '$HERMES_HOME/plugins/advanced-delegation/store.py'); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
   r = ry.YAML(typ='safe').load(open('<config.yaml>'))['delegation']['backends']['model_map']['options']
   print([(x['name'], m.validate_route(x, [o for o in r if o is not x]) or 'OK') for x in r])
   EOF
   ```
   Replace `$HERMES_HOME` with the real path, because the quoted heredoc does not expand it. The check covers provider known, effort valid and tier offered. It does not prove a spawn works, so run one real delegated task per route after the restart.
5. Fallback (the step that actually protects a subscription limit): add a top-level `fallback_providers:` list (each entry needs `provider` + `model`; named custom providers such as `litellm` work) and the same key on the expensive routes. Set `fallback.min_switch_reset_seconds: 120` so a limit that resets within 2 minutes gets waited out instead of switching models. Check that each entry resolves before the PR:
   ```bash
   cd /opt/hermes && .venv/bin/python -c "import sys; sys.path.insert(0,'.'); from agent.auxiliary_client import resolve_provider_client as r; print(r('openai-codex','gpt-6.1-sol'))"
   ```
   Docs: `/docs/user-guide/features/fallback-providers` (the `hermes fallback` CLI writes the same key).
6. Auxiliary: move cheap internal calls (titles, skills hub, MCP, Kanban triage) to a cheap or fast model. Keep `compression` and the `approval` classifier on a strong model, because a weak model there loses context or misjudges risky commands.

## Explaining it to the user
Users expect routing to be fully automatic and to stop them running out of Claude. Say these points up front:
- The parent agent picks a route for each subagent from the descriptions. `default:` is only the fallback for tasks that get no route. Don't call it "the default model", because that sounds like a lock.
- The main chat model never gets routed. A task that isn't split into subagents runs entirely on the main model.
- Routing alone doesn't save a plan's limit when the main model and the default route are on the same plan (Opus + Sonnet both use Claude). Fallback providers are what keep work going at the limit. Recommend fallback first, then cheaper aux models.
- Mitch keeps `balanced` (Sonnet) as the default route and wants Codex as the fallback, not as the default.

## Pitfalls
- Route schema changes apply to new sessions only. The running chat keeps its old `delegate_task` schema.
- Profile routes don't carry the target profile's memory, only its model, skills, keys and SOUL.md. Use Kanban when the worker needs its own memory or results that persist.
- `/opt/hermes/bin/hermes` is a `/bin/sh` launcher. Run Hermes-internal Python with `/opt/hermes/.venv/bin/python`, which has `ruamel.yaml` but no `pyyaml`.
