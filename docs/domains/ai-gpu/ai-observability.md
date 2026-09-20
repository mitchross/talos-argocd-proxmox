# AI gateway and analytics

**Which model answered?** Open Grafana `/d/pi-routing`.
**Why did that turn escalate?** Open `langfuse.vanillax.me`, filter tag `pi`.

## Who measures what

| Service | Answers |
|---|---|
| Grafana `/d/pi-routing` | local vs paid ratio, escalations, spend |
| Grafana `/d/ai-gateway-analytics` | gateway requests, tokens, latency, failures |
| Langfuse | per-trace inputs/outputs, tokens, sessions, routing metadata |
| Prometheus | throughput, vLLM KV capacity, GPU utilisation |

Local traffic is **LiteLLM → vLLM**. Paid traffic is **LiteLLM → OpenRouter**.
LiteLLM exports to Langfuse via `langfuse_otel` and to Prometheus via its
`prometheus` callback.

## Reading the Qwen / DeepSeek split

`pi-withflash` reports the `pi-auto` alias, never the backend that answered.
LiteLLM tags every request with two model labels, and the split lives in the gap
between them:

| Label | Meaning | Value on an auto-routed turn |
|---|---|---|
| `requested_model` | what the client asked for | `pi-auto` |
| `model` / `litellm_model_name` | what actually ran | `qwen3.8-27b-auto` or `~deepseek/deepseek-flash-latest` |

`litellm_proxy_total_requests_metric_total` carries **only** `requested_model`,
so it cannot show the split. Use
`litellm_deployment_success_responses_total`, whose `litellm_model_name` is the
resolved deployment.

Two traps, both caused by sparse Pi traffic, both failing in the reassuring
direction:

1. A LiteLLM counter that first appears at its **full value** makes `increase()`
   return zero, so a real escalation reads as "never fired". Use
   `max_over_time(...[$__range])` for totals and a cumulative line for spend.
2. `histogram_quantile` returns `NaN` when every bucket rate is zero, which a
   handful of classifier calls guarantees. Use a `sum`/`count` average.

In Langfuse the resolved backend is `providedModelName`. Scope every widget with
the tag filter `tags any of [pi]`; without it, Open WebUI and the other gateway
clients count as Pi turns. Per trace, check `routing_decision.cause`:
`llm_classifier` means the task was judged, `default_model_fallback` means
classification failed and fell back.

Langfuse dashboards live in the Langfuse database, not in Git. Recreate them
through the UI, or through `dashboardWidgets.create` plus
`dashboard.updateDashboardDefinition`, after a rebuild.

## Routes and credentials

| Caller | Endpoint | Auth |
|---|---|---|
| Pi (all gateway routes) | `https://litellm.vanillax.me/v1` | LiteLLM key on the workstation |
| Apps | `http://litellm-service.litellm.svc.cluster.local:4000/v1` | namespace ExternalSecret |
| LiteLLM → Qwen | `http://vllm-service.vllm.svc.cluster.local:8080/v1` | local placeholder |
| LiteLLM → DeepSeek | OpenRouter | `litellm-secrets` ExternalSecret |
| LiteLLM → Langfuse | `http://langfuse-web.langfuse.svc.cluster.local:3000` | project keys |
| Direct diagnostics | `https://vllm.vanillax.me/v1` | bypasses all telemetry |

Every namespace receives `homelab-prod/litellm/master_key` through External
Secrets. No keys in ConfigMaps or workflow JSON. This is a shared gateway
credential, not a per-app budget or access control.

## Storage

| Store | Holds | Backup |
|---|---|---|
| PostgreSQL | identity, projects, configuration | kopiur, restore-before-bind |
| ClickHouse | AI observations | kopiur, restore-before-bind |
| Valkey | queue | **exempt** — losing it loses in-flight observations |
| RustFS | event payloads, media, exports | separate bucket lifecycle |

Chart 2.1.0, app 4.24.0. Chart-bundled stores are disabled; the app owns
PostgreSQL, ClickHouse and Valkey so no database operator is needed. A Sync hook
creates the RustFS bucket before web and worker start.

Do not describe this as lossless messaging. Keep all stores consistent when
planning a restore, and test recovery with synthetic observations first.

Langfuse v4 uses its new observations data model. The pinned LiteLLM container
ships legacy Langfuse SDK 2.59.7, so the plain `langfuse` callback is unusable —
`langfuse_otel` supplies the v4 header and exports to
`/api/public/otel/v1/traces`. Read with Observations API v2; legacy traces APIs
return 404 on a fresh v4 install.

## Verify a deployment

Roughly 15 minutes.

1. Confirm `my-apps-langfuse`, `my-apps-litellm`, `my-apps-open-webui` and
   `monitoring-prometheus-stack` are Synced/Healthy.
2. Sign into Langfuse and open **Homelab AI**. An empty chart means nothing
   until you have confirmed the project exists.
3. Send synthetic traffic:
   ```bash
   kubectl -n litellm exec -i deploy/litellm -- python - < scripts/smoke-litellm.py
   ```
   Expect PASS for thinking-off, streamed medium with usage, tool invocation,
   tool-result followup and vision. Record the printed
   `ai-observability-...` session marker.
4. In Langfuse Observations, filter by that `session_id` and clear the
   root-only filter. Expect at least five generations with model, input/output,
   positive token usage and latency. **Intake HTTP success alone proves
   nothing** — only stored observations do.
5. Check backups:
   ```bash
   kubectl -n langfuse get secret kopiur-rustfs
   kubectl -n langfuse get snapshotpolicy,snapshotschedule,restore,snapshot
   ```
   Both database policies exist and snapshots reach `Succeeded` with non-zero
   files. A brand-new empty PVC is not a tested restore.

Check the adapter before deploying a LiteLLM bump:

```bash
kubectl -n litellm exec -i deploy/litellm -- python - < scripts/verify-litellm-langfuse.py
```

This uses synthetic in-memory spans, makes no model requests, and catches a
pinned-adapter incompatibility before it reaches the cluster.

## When telemetry breaks

| Symptom | Cause | Fix |
|---|---|---|
| Requests work, no traces | adapter or key mismatch | run the adapter check above |
| Empty charts, project missing | signed into the wrong project | open **Homelab AI** |
| Traces stop after a version bump | v4 data-model or SDK drift | re-run the adapter check, then step 4 |
| TTFT panel empty | no streaming traffic | send a streamed request |

Availability and restart panels never prove ingestion. Only step 4 does.

Telemetry is optional to inference. If Langfuse is down, model requests still
succeed and observations for that window are lost.

## Upstream

- [LiteLLM Auto Routing](https://docs.litellm.ai/docs/proxy/auto_routing)
- [LiteLLM OpenRouter provider](https://docs.litellm.ai/docs/providers/openrouter)
