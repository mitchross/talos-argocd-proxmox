# Troubleshooting

### Voice not working
1. Check `stt.enabled: true` in config.yaml
2. Verify provider: `python -c "import pm; pm.sync_venv(['stt-whisper'], explicit=True)"` or set API key
3. In gateway: `/restart`. In CLI: exit and relaunch.

### Tool not available
1. `hermes tools` — check if toolset is enabled for your platform
2. Some tools need env vars (check `.env`)
3. `/reset` after enabling tools

### Model/provider issues
1. `hermes doctor` — check config and dependencies
2. `hermes auth` — re-authenticate OAuth providers (or `hermes auth add <provider>`)
3. Check `.env` has the right API key
4. **Copilot 403**: `gh auth login` tokens do NOT work for Copilot API. You must use the Copilot-specific OAuth device code flow via `hermes model` → GitHub Copilot.

### Changes not taking effect
- **Tools/skills:** `/reset` starts a new session with updated toolset
- **Config changes:** In gateway: `/restart`. In CLI: exit and relaunch.
- **Code changes:** Restart the CLI or gateway process

### web_extract shows a stale page (result caching)
`web_search`/`web_extract` cache results for 20 minutes (PR #94618) — a
repeat fetch of the same URL within the TTL is served from cache, which
can look like "my website changes aren't showing up."

Automatic carveouts (always fetched live, never cached):
- localhost / 127.0.0.1 / `*.local` / `*.localhost` / single-label LAN
  hostnames / private + link-local IP ranges (dev servers, hot-reload
  builds, chat-GUI artifact previews)
- URLs matched by `security.website_blocklist`
- failed responses and keyless-rescue-served responses

Developing a site tested over the PUBLIC internet (Vercel/Netlify
preview, ngrok/cloudflared tunnel, staging domain)? Public DNS isn't
auto-carved-out — list the host in config.yaml:

```yaml
web:
  cache_exempt_hosts:      # always fetched live; effective immediately
    - mysite.vercel.app
    - "*.ngrok-free.app"
    - mysite.dev           # suffix match: also covers preview.mysite.dev
```

Blunt instruments: `web.cache_ttl_minutes: 1` (min) or
`web.cache_enabled: false` disables both caches entirely.

### web_extract fails: "search-only backend and cannot extract URL content"
`web.extract_backend` is empty, so extract falls back to the search backend (e.g. OpenAI native search), which can't fetch pages. Set an extract backend: `web.extract_backend: firecrawl|tavily|exa|parallel|keenable` plus its API key in `.env` (or the secret store that feeds it). Until then, `curl` the URL from the terminal or use the browser tool.

### Hindsight recall keeps returning the same few stale memories
Retain can be healthy while recall is starved. The Hindsight plugin's `recall_types` defaults to `observation` only (auto-recall and the `hindsight_recall` tool both use it). Observations come from server-side consolidation, so a stalled consolidation freezes recall at whatever observations exist.
1. Compare `GET <api>/v1/default/banks/<bank>/stats`: low `total_observations`, high `pending_consolidation` and an old `last_consolidated_at` mean consolidation is stalled. A direct `POST .../memories/recall` without a `types` filter returning the right facts confirms it.
2. Find stuck ops: `GET .../operations?status=processing`. An op that has been processing for hours and is held by a worker pod that no longer exists (server log `[WORKER_STATS] ... others: <dead-pod>:N`) blocks every later consolidation for the bank. Before cancelling, compare `pending_consolidation` with the database's memory limit: tens of thousands of pending facts start a run that can saturate a small Postgres (CPU, ~1 GB/s reads, memory at its cap), and short `pg_isready` liveness timeouts then kill it in a loop. Raise the DB memory limit and probe timeout first, or watch the DB pod closely right after. Release it with Hindsight's admin CLI, which requeues the job instead of discarding it: `kubectl -n <ns> exec deploy/<hindsight> -- hindsight-admin decommission-worker <dead-worker-id> --yes` (or `decommission-workers` for all). `DELETE .../operations/<id>` also works but drops the job. The queued consolidation starts within seconds; watch `total_observations` climb and `pending_consolidation` fall.
   **Prevent it:** set `HINDSIGHT_API_WORKER_ID` to a fixed value (Hindsight's install docs recommend it for production). Without it the worker id is the pod hostname, and on startup a worker reclaims only jobs under its own id, so every restart strands the old pod's jobs. With a fixed id, roll out one pod at a time so two pods never share it. Use `Recreate` on a new Deployment, but on an existing Argo-managed one use `RollingUpdate` with `maxSurge: 0, maxUnavailable: 1`; see the gitops skill for why. The switchover restart itself strands one last job under the old hostname id, so plan one final `decommission-worker` right after it. The Helm chart's StatefulSet does this via stable pod names. A Hindsight pod restart orphans every op it was processing (retains too), so a `processing` op whose `updated_at` predates the pod's start time is dead. `failed` ops with "exceeded the 3600s wall-clock limit for 'batch_retain'" mean the retain LLM is too slow; raise `HINDSIGHT_API_RETAIN_WALL_TIMEOUT` or speed up that model.
3. Make recall robust: in `$HERMES_HOME/hindsight/config.json` set `"recall_types": "observation,world,experience"`. That file replaces the env-derived plugin config, so also set `mode`, `api_url`, `bank_id` and `recall_budget`. The API key may stay in `HINDSIGHT_API_KEY`. If config.yaml/skills are seeded from Git on pod start, change the seed rather than the volume.
4. Fix stale *facts* without deleting them: `PATCH .../memories/<id>` with `{"state":"invalidated","reason":"..."}` (reversible). Never use `DELETE .../memories`, which clears the bank.

### Desktop app: DevTools / renderer console
Open with `Ctrl+Shift+I` (Linux/Windows) or `Cmd+Opt+I` / View → Toggle Developer Tools (macOS). F12 also works unless the device-local "disable F12" preference is on. Works in packaged builds; opens detached. The shortcut is not in the docs. It is defined in `apps/desktop/electron/main.ts` (`installDevToolsShortcut`), so re-check there if it seems to have changed.

### Desktop app: whole window semi-transparent on Linux
The translucency default (intensity 29, the macOS bucket) can reach the native `setOpacity` on Linux, both X11 and native Wayland. Settings → Appearance hides the control there. Editing `<userData>/translucency.json` (`~/.config/Hermes/`) alone does not stick, because the renderer re-seeds the default and main writes it back. Workaround: in the DevTools Console run
```js
localStorage.setItem('hermes.desktop.translucency.v2', JSON.stringify({mode:'clear', base:{intensity:0}, light:{}, dark:{}}))
```
then fully quit and relaunch (a reload is not enough). Before giving the workaround, check whether the upstream fix has shipped (`gh issue list -R NousResearch/hermes-agent --search "opacity linux"`). If it has, the answer is to update instead.

### Skills not showing
1. `hermes skills list` — verify installed
2. `hermes skills config` — check platform enablement
3. Load explicitly: `hermes -s name` (or the skill's own `/<name>` slash command)

### Gateway issues
Check logs first:
```bash
grep -i "failed to send\|error" ~/.hermes/logs/gateway.log | tail -20
```

Common gateway problems:
- **Gateway dies on SSH logout**: Enable linger: `sudo loginctl enable-linger $USER`
- **Gateway dies on WSL2 close**: WSL2 requires `systemd=true` in `/etc/wsl.conf` for systemd services to work. Without it, gateway falls back to `nohup` (dies when session closes).
- **Gateway crash loop**: Reset the failed state: `systemctl --user reset-failed hermes-gateway`
- **Turns lost on every container/pod restart (Docker image, s6-overlay)**: check the init's kill grace with `ps -eo args | grep shutdownd` (`-g 3000` = SIGKILL 3 s after SIGTERM). Raising `agent.restart_drain_timeout` or the pod's `terminationGracePeriodSeconds` does not help while that holds. Before changing anything, check whether the upstream image fix has shipped (`gh issue list -R NousResearch/hermes-agent --search "s6 shutdown gateway"`). The community workaround is a `/etc/cont-finish.d` hook that runs `s6-svc -d` and then `s6-svwait -D -t <ms>` on `/run/service/gateway-*`, plus `S6_KILL_FINISH_MAXTIME` above that wait. `S6_SERVICES_GRACETIME` has no effect, because gateways are dynamic slots in `/run/service`. Desktop and dashboard chat turns are dropped on a SIGTERM restart no matter how long the drain is; only fewer restarts or the upstream fix helps there. Prefer in-band `/restart`, which waits for turns (`restart_after_turn_timeout`).

### Cron job: one run failed with "Hermes can't reach the model provider"
1. Read the run file: `$HERMES_HOME/cron/output/<job_id>/<timestamp>.md` (prompt, response, traceback). `hermes cron list` shows the last status per job.
2. Bound the outage window across ALL sessions, not just the job: `grep -a APIConnectionError $HERMES_HOME/logs/agent.log*` for that hour. If chats failed in the same minutes, it was a connectivity gap from the gateway host, not the job.
3. Check the provider status page for an incident in that window, and node-level network events (CNI agent restarts on the gateway's own node) before blaming the cluster.
4. Re-run with `cronjob(action='run', job_id=...)`. A clean rerun plus no repeat at the next schedule closes it; say the cause is unknown rather than guessing.

### "Where do I see cron output?" (desktop app)
Scheduled jobs pane → click the job → Run history rows. Files live in `$HERMES_HOME/cron/output/<job_id>/`. Deliver `local` saves only. The desktop app shows results only while it is open, so for phone or away-from-desk alerts use a messaging platform (Telegram has a QR quick setup in Desktop → Messaging) or have a `no_agent` script post to a GitHub issue, which notifies via GitHub. The app is enough if the user only reads results at the desk. When the user treats Desktop as their only interface, lead with the in-app path and offer a messaging platform only as an opt-in for away-from-desk alerts. If they find daily report text hard to read and want current state, a live dashboard (e.g. Grafana) beats tuning delivery.

### Platform-specific issues
- **Discord bot silent**: Must enable **Message Content Intent** in Bot → Privileged Gateway Intents.
- **Slack bot only works in DMs**: Must subscribe to `message.channels` event. Without it, the bot ignores public channels.
- **Windows-specific issues** (`Alt+Enter` newline, WinError 10106, UTF-8 BOM config, line endings): see `references/windows-quirks.md`.

### Auxiliary models not working
If `auxiliary` tasks (vision, compression, session_search) fail silently, the `auto` provider can't find a backend. Either set `OPENROUTER_API_KEY` or `GOOGLE_API_KEY`, or explicitly configure each auxiliary task's provider:
```bash
hermes config set auxiliary.vision.provider <your_provider>
hermes config set auxiliary.vision.model <model_name>
```

### "Reset permissions" / auto-approving everything
See `references/security-privacy.md` — wipe the "Always allow" stores, don't touch yolo mode.

