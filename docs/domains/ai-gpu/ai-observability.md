# AI observability: Langfuse, LiteLLM and Grafana

Git-declared configuration, audited 2026-09-06. The Langfuse migration and
PostHog retention fix require the user to merge the PR and ArgoCD to sync.
Manifest validation is not proof of live trace ingestion.

## What each service measures

| Service | Role |
|---|---|
| Langfuse | AI inputs/outputs, generations, tokens, latency, session grouping, scores and evaluation workflows |
| LiteLLM | Authenticated model gateway; exports generation telemetry and request metrics |
| Prometheus / Grafana | Request failures, latency, throughput, vLLM KV capacity/preemptions and GPU utilization |
| PostHog | Product events, funnels, feature flags and browser session replay |

Pi and Open WebUI use **LiteLLM → vLLM**. LiteLLM exports observations to
self-hosted Langfuse using `langfuse_otel`, alongside its `prometheus` callback.
PostHog's AI callbacks are removed; its deployment and existing data remain.
Historical PostHog AI events/Kafka backlog are not imported into Langfuse.

A gateway observes model calls and tool-call responses. It does not automatically
observe local tool execution, file changes, or every internal agent step. Use
application instrumentation for those spans when building agents. Evaluation
scores are also not automatic: add a small labeled dataset and explicit scoring
before treating model speed as evidence of answer quality. This deployment does
not enable paid judges or background model calls.

## Routes and credentials

| Caller | Endpoint | Authentication |
|---|---|---|
| Pi | `https://litellm.vanillax.me/v1` | LiteLLM key in local Pi `auth.json` |
| Open WebUI | `http://litellm-service.litellm.svc.cluster.local:4000/v1` | `open-webui-litellm` ExternalSecret |
| LiteLLM inference | `http://vllm-service.vllm.svc.cluster.local:8080/v1` | Existing local placeholder |
| LiteLLM telemetry | `http://langfuse-web.langfuse.svc.cluster.local:3000` | Langfuse project public/secret keys |
| Langfuse UI | `https://langfuse.vanillax.me` | Initial owner credentials in 1Password |
| Direct diagnostics | `https://vllm.vanillax.me/v1` | Bypasses gateway observations |

Before merging the new app, unlock the 1Password desktop app with CLI
integration enabled (or sign into `op`), then run:

```bash
python3 scripts/bootstrap-langfuse-secrets.py
```

Expected: the item is created or existing fields are validated. The helper
preserves existing credentials and prints no values. The Connect token used by
External Secrets has read-only vault access and cannot perform this creation.

`homelab-prod/langfuse` holds `public-key`, `secret-key`, `admin-email`,
`admin-password`, `salt`, `encryption-key`, `nextauth-secret`, and the three
store passwords. ExternalSecrets copy them into the owning namespaces.
Headless initialization creates the Vanillax organization and Homelab AI project
with the same project keys used by LiteLLM. Public signup and vendor telemetry
are disabled. Initialization only seeds missing entities; editing the seed
password/key later is not an account/key rotation procedure. Keep the salt and
encryption key with database backups; replacing them can make stored credentials
unusable. Never paste secret values into manifests or smoke-test output.

Prometheus authenticates `/metrics` with the existing LiteLLM master key.
The hash-suffixed ConfigMap rolls LiteLLM on callback/configuration edits.
Its 30-minute timeout and latency buckets preserve long-running requests.
Local Qwen cost is recorded as zero, excluding hardware and electricity.
Prompts and completions are stored in Langfuse, not just anonymous counters.
Use synthetic input when verifying ingestion and set retention deliberately in
the project settings before collecting large volumes of real conversations.

The [Pi guide](pi-agent-local-dev.md) remains authoritative for medium thinking,
explicit off/low/medium/xhigh, the Qwen sampler and compaction. The model,
FP8 weights/KV, TP=2, native vision, 262,144-token ceiling and disabled MTP remain
unchanged. The gateway smoke test is not another full-context endurance test.

## Deployment and persistence

The application at `my-apps/ai/langfuse` is discovered automatically by ArgoCD.
It pins the maintained Langfuse chart **2.1.0** and app **4.24.0**. Chart-owned
web/worker pods use app-owned PostgreSQL, standalone ClickHouse and Valkey;
all chart-bundled stores are disabled. This avoids adding database operators.
The namespace and secrets precede stores; a Sync hook creates the scoped RustFS
bucket before web and worker start. Database migrations are owned by Langfuse.

PostgreSQL holds identity/project/configuration data. ClickHouse holds AI
observations. Both have Longhorn volumes and kopiur restore-before-bind backups.
Valkey has a persistent queue with no eviction, but is backup-exempt under repo
policy: catastrophic queue-volume loss can lose in-flight observations even if
S3 payloads survive. Do not describe this as a lossless messaging system.
RustFS holds event payloads, media and exports under separate `langfuse` bucket
prefixes. Its storage/backup lifecycle is separate from kopiur database snapshots.
Keep all stores consistent when planning a restore; test recovery with synthetic
observations before relying on it for enterprise-style retention guarantees.

Langfuse v4 defaults to its new observations data model. The pinned LiteLLM
container includes legacy Langfuse SDK 2.59.7, so the `langfuse` callback is
unsuitable. Its existing `langfuse_otel` integration supplies the v4 ingestion
header and exports to `/api/public/otel/v1/traces`. No LiteLLM upgrade or custom
SDK/kernel is needed. Use Observations API v2 for reads; legacy traces APIs
return 404 on fresh v4 installations.

## Adapter verification before deployment

```bash
kubectl -n litellm exec -i deploy/litellm -- python - < scripts/verify-litellm-langfuse.py
```

Expected: PASS for the v4 endpoint/header/auth, session metadata, tool output,
usage and zero local cost. This uses synthetic in-memory spans without making
model requests or exporting telemetry; it catches pinned-adapter incompatibility.

## Verification after ArgoCD sync

1. Confirm `my-apps-langfuse`, `my-apps-litellm`, `my-apps-open-webui` and
   `monitoring-prometheus-stack` are Synced/Healthy. Check the Langfuse
   ExternalSecret, bucket hook, database migrations and both application pods.
2. Sign into Langfuse using `homelab-prod/langfuse` owner credentials and open
   **Homelab AI**. Confirm the project exists before interpreting empty charts.
3. Send five synthetic requests through the gateway:

   ```bash
   kubectl -n litellm exec -i deploy/litellm -- python - < scripts/smoke-litellm.py
   ```

   Expected: PASS for thinking off, streamed medium with usage/reasoning,
   tool invocation, preserved tool-result followup and vision. Record the
   printed `ai-observability-...` session marker. These checks prove forwarding;
   the next step proves telemetry delivery.
4. Allow batching/ingestion to finish. In Langfuse Observations, filter by that
   `session_id` and clear the default root-only filter if necessary. Expect
   at least five generation observations named for the smoke cases, with model,
   input/output, positive token usage and latency. Inspect the tool arguments
   and followup result. Check the image request still appears as a generation;
   browser media upload/download is a separate check. Retries may produce more
   than five records. Intake HTTP success alone is insufficient.
5. Open Grafana's **AI Gateway and Analytics** dashboard
   (`/d/ai-gateway-analytics`). Expect LiteLLM scrape=1, request/token/latency
   samples and available Langfuse web/worker replicas. Availability/restart
   panels do not prove ingestion; use step 4. TTFT needs streaming traffic.
   **vLLM Inference** and the GPU dashboard retain engine/hardware metrics.
6. Verify backup configuration and the first successful snapshots:

   ```bash
   kubectl -n langfuse get secret kopiur-rustfs
   kubectl -n langfuse get snapshotpolicy,snapshotschedule,restore,snapshot
   ```

   Expected: both database policies/restores exist and snapshots eventually
   succeed with non-zero files. A brand-new empty PVC is not a tested restore.

For controlled comparisons, keep prompt dataset, concurrency, input/output
lengths, reasoning level and warm/cold-cache conditions fixed. Compare latency,
TTFT, tokens per second, errors and a correctness score together. A higher token
rate alone does not establish a better agent or longer usable context.

## Failure handling and rollback

If inference fails, compare a synthetic direct vLLM request and inspect LiteLLM
logs/model routing/ExternalSecret readiness. Keep model and GPU settings fixed
while diagnosing gateway authentication. If telemetry stalls, inspect LiteLLM's
OTel export errors, Langfuse web/worker logs, store connectivity and migrations.
Do not reset queues, recreate databases or change project keys to clear errors.

Rollback routing/callback changes through Git while retaining the Langfuse
application's persistent stores. Removing the entire auto-discovered app can
cascade deletion of its resources; first preserve the desired storage in Git
and confirm backups. Pi can temporarily use direct vLLM with its local
placeholder key, or restore its local provider/auth backup. Direct calls retain
vLLM/GPU metrics but bypass LiteLLM and Langfuse observations.

PostHog remains independently maintained for product analytics and replay. Its
30-day retention compatibility fix and verification are documented in the
[PostHog runbook](../../posthog-self-host-k8s.md).

## Upstream references

- [Langfuse Kubernetes deployment](https://langfuse.com/self-hosting/deployment/kubernetes-helm)
  and [headless initialization](https://langfuse.com/self-hosting/administration/headless-initialization).
- [Langfuse v4 compatibility and API changes](https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4).
- [LiteLLM Langfuse OTel integration source](https://github.com/BerriAI/litellm/blob/v1.99.1/litellm/integrations/langfuse/langfuse_otel.py)
  (also inspected inside the pinned live image) and
  [Prometheus integration](https://docs.litellm.ai/docs/proxy/prometheus).
