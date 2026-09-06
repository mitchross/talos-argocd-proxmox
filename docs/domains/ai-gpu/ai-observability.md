# AI gateway metrics and PostHog analytics

Git-declared configuration, audited 2026-09-06. Changes take effect after the
user merges the PR and ArgoCD syncs; a healthy Deployment alone does not prove
that metrics or AI events are being stored.

Pi and Open WebUI send requests to **LiteLLM → vLLM**. LiteLLM reports request
counts, failures, tokens, and latency to Prometheus and sends `$ai_generation`
events to self-hosted PostHog. vLLM separately reports engine throughput, KV
occupancy, preemptions, and scheduling. GPU metrics remain in the GPU dashboard.
These layers answer different questions: who called the model, what happened
in a conversation, and what the inference hardware was doing.

## Routes and credentials

| Caller | Endpoint | Authentication |
|---|---|---|
| Pi | `https://litellm.vanillax.me/v1` | LiteLLM key in local Pi `auth.json` |
| Open WebUI | `http://litellm-service.litellm.svc.cluster.local:4000/v1` | `open-webui-litellm` Secret from 1Password |
| LiteLLM | `http://vllm-service.vllm.svc.cluster.local:8080/v1` | Existing local vLLM placeholder |
| Diagnostics / other direct clients | `https://vllm.vanillax.me/v1` | Existing local vLLM placeholder; bypasses gateway analytics |

The Pi provider ID remains `vanillax-vllm/qwen3.8-27b`; its explicit thinking
mapping, sampler extension, compaction, and 262,144-token ceiling are unchanged.
See the [Pi guide](pi-agent-local-dev.md). LiteLLM's Qwen timeout and internal
HTTPRoute allow 30 minutes, matching WebUI's request timeout. Gateway latency
histogram buckets also extend to 30 minutes; the built-in 600-second ceiling
would understate slow-request percentile estimates. Long-context
capacity was measured directly on vLLM; short gateway probes do not constitute
a second full-context endurance test.

`homelab-prod/litellm/master_key` authenticates both clients and the Prometheus
scrape. The ServiceMonitor references its namespace-local Secret. LiteLLM's
`callbacks: ["prometheus"]` exposes `/metrics`; explicit authentication keeps
that endpoint protected. The hash-suffixed configuration ConfigMap changes the
Deployment's volume reference when edited, so ArgoCD rolls the pod and actually
loads the new callbacks. PostHog success/failure callbacks remain enabled.

PostHog uses `homelab-prod/litellm/posthog_api_key`: this must be the existing
project token from PostHog project settings. A newly generated random string
is not a valid project key. The audit confirmed it matched project 1. LiteLLM's
PostHog callback records prompt/completion content as well as token counts and
latency. This is self-hosted conversation storage, not just anonymous counters.
Local Qwen cost is recorded as zero; that excludes electricity/hardware cost.

## Why PostHog looked healthy while AI analytics were empty

The audit found working vLLM metrics and LiteLLM inference, but authenticated
LiteLLM `/metrics` returned 404. PostHog accepted both ordinary and AI captures
with HTTP 200. Ordinary events reached ClickHouse; AI events did not.

Rust capture was writing AI events to `events_plugin_ingestion_ai`, which had
122 retained messages and no consumer group at the audit snapshot. The pinned
Node combined consumer subscribed to five other topics. `posthog.ai_events`
had zero rows. This was a missing consumer, not an API-key or model problem.

The dedicated `ingestion-ai` Deployment runs the same Node digest as the
existing ingestion service, in supported `ingestion-v2` mode with:

- topic `events_plugin_ingestion_ai` and group `clickhouse-ingestion-ai`;
- `INGESTION_AI_EVENT_SPLITTING_ENABLED=false`, keeping full AI payloads in
  `clickhouse_events_json` → shared `posthog.events`;
- the same Postgres/Redis/GeoIP configuration, bounded memory, and an owned VPA.

The live project's `ai-events-table-rollout` read flag is **false**. The pinned
web resolver therefore reads shared events. Enabling event splitting would
strip prompts/completions from that table and place them in `ai_events`, which
the current UI does not read. Keep splitting off until a coordinated read/write
migration is explicitly planned. An empty dedicated `ai_events` table is
expected with this compatibility configuration; it is not a delivery failure.

The pinned consumer defaults to `auto.offset.reset=earliest`, so the new group
can process retained backlog. Expired Kafka records cannot be recovered by this
change. It does not reset offsets, delete topics, or upgrade PostHog images.

## Verify after ArgoCD sync

Prerequisites: repository checkout, `kubectl` access, and permission to read
Prometheus/PostHog. The smoke test sends five synthetic model requests and a
small generated image; it does not send a repository or user conversation.

1. Check `my-apps-litellm`, `my-apps-open-webui`, `my-apps-posthog`, and
   `monitoring-prometheus-stack` are Synced/Healthy in ArgoCD. Confirm the new
   `ingestion-ai` Deployment is ready and WebUI's ExternalSecret is ready.
2. Open Grafana's **AI Gateway and Analytics** dashboard (`/d/ai-gateway-analytics`).
   LiteLLM scrape must be 1 and the AI consumer member count must be positive.
   Zero traffic can be legitimate; no consumer must never be interpreted as
   zero queue lag. Existing **vLLM Inference** remains the engine dashboard.
3. Run the forwarding smoke test:

   ```bash
   kubectl -n litellm exec -i deploy/litellm -- python - < scripts/smoke-litellm.py
   ```

   Expected: `PASS` for thinking off, streamed medium with usage/reasoning,
   tool invocation, tool-result followup with preserved history, and vision.
   Record the printed `ai-observability-...` marker. This proves inference
   forwarding only; finish the storage check below.
4. Wait for callback batching and ingestion, then inspect the queue:

   ```bash
   kubectl -n posthog exec deploy/kafka -- rpk group describe clickhouse-ingestion-ai --brokers kafka:9092
   ```

   Expected: an active member, committed offsets, and lag draining toward zero.
   Empty/unregistered group means the consumer is still missing or unhealthy.
5. Verify actual event storage, replacing `<marker>` with the printed marker:

   ```bash
   kubectl -n posthog exec deploy/clickhouse -- clickhouse-client --query "SELECT count() FROM posthog.events WHERE distinct_id = '<marker>'"
   kubectl -n posthog exec deploy/clickhouse -- clickhouse-client --query "SELECT count() FROM posthog.events WHERE distinct_id = '<marker>' AND JSONHas(properties, concat(char(36), 'ai_input')) AND JSONHas(properties, concat(char(36), 'ai_output_choices'))"
   ```

   Expected: at least five shared events, with full input/output properties,
   after the consumer drains (retries/at-least-once delivery can create duplicates).
   `char(36)` is the dollar-sign prefix in PostHog property names and avoids
   shell expansion in the command. Find the same trace
   events in PostHog's LLM analytics for project 1, including model, usage,
   latency, and prompt/completion. If SQL has rows but the UI does not, inspect
   project/time filters and PostHog query settings separately.

The Grafana gateway panels should acquire request/token/latency samples after
the synthetic traffic. TTFT requires streaming traffic. A callback's HTTP 200
is an intake acknowledgement, not end-to-end delivery confirmation.

## Failure handling and rollback

If inference fails through the gateway, compare the same synthetic request with
the direct vLLM endpoint. Check LiteLLM logs and its model list before changing
GPU or model configuration. WebUI's old placeholder key will return 401 against
LiteLLM; inspect ExternalSecret readiness, never paste the key into Git.

If AI events stall, inspect `ingestion-ai` logs, Kafka group offsets, and
ClickHouse's `kafka_events_json` consumer. Keep the queue intact. Fix topic,
image/config, or schema mismatches through Git; do not reset offsets or recreate
the data layer. The [PostHog guide](../../posthog-self-host-k8s.md) owns migration
and storage recovery rules.

Rollback cluster changes by reverting the scoped Git commit and letting
ArgoCD reconcile. Pi can temporarily use `https://vllm.vanillax.me/v1` with its
local placeholder key, or restore its backed-up provider/auth files. Direct
requests retain vLLM/GPU metrics but do not produce LiteLLM/PostHog analytics.

## Sources and owning configuration

- [LiteLLM Prometheus integration](https://docs.litellm.ai/docs/proxy/prometheus)
  and [PostHog callback](https://docs.litellm.ai/docs/observability/posthog_integration).
- [PostHog Rust capture configuration](https://github.com/PostHog/posthog/blob/master/rust/capture/src/config.rs).
  The deployed Node image was also inspected directly: `servers/ingestion-general-server.js`,
  `ingestion/config.js`, `event-processing/split-ai-events-step.js`, and
  `kafka/consumer.js`, plus the web `hogql_queries/ai/ai_table_resolver.py` read
  gate; current master must not substitute for pinned-image behavior.
- [LiteLLM application](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/ai/litellm),
  [AI consumer](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/posthog/core/ingestion-ai.yaml),
  and [dashboard](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/prometheus-stack/dashboards/ai-gateway-analytics.json).
