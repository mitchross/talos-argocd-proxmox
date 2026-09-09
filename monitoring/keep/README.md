# Keep alert view

Alertmanager sends events to Keep. Critical alerts do not automatically call
Holmes or the local model. `backend.provision.workflows` is deliberately empty;
Holmes remains parked until explicitly enabled for an investigation.

The chart includes a workflow checksum in the backend pod template, so changing
the provisioned list rolls the backend. Keep 0.52.1 removes previously provisioned
workflows at startup when no workflows directory or inline workflow is configured.
See its [provisioning code](https://github.com/keephq/keep/blob/v0.52.1/keep/workflowmanager/workflowstore.py)
and [provisioning guide](https://docs.keephq.dev/deployment/provision/workflow).

After sync, check that the backend rollout completes and `holmes-rca` is absent
from the workflow list. Confirm alerts still arrive. This removes the automatic
trigger; it does not deploy the Holmes console or add an investigation interface.
A Git revert restores the workflow and automatic critical-alert calls.

## Authenticated inference

The existing `llama-cpp-local` provider name is retained so Keep updates its
saved authentication in place on startup. It now uses LiteLLM. The
`keep-litellm` ExternalSecret reads the existing 1Password `litellm/master_key`
into `LITELLM_API_KEY`; Keep 0.52.1's provision parser expands
`$(LITELLM_API_KEY)` before saving the provider. Changing provisioned settings
changes the chart checksum and rolls the backend.
The chart imports the credential with `backend.envFromSecrets`; its
`backend.env` template supports literal values only and drops `valueFrom`.

The provider type remains `vllm`, whose implementation appends
`/v1/completions` to `api_url`; its configured gateway URL therefore ends at
`:4000`. Workflow queries must explicitly select `model: qwen3.8-27b`, since
the upstream provider's default model is unrelated to this deployment. No AI
workflow is enabled by this migration. Separately installed UI providers are
not reconciled by this declaration. The read-only migration audit found only
the provisioned `llama-cpp-local` entry, with no separate UI providers.

After sync, verify `keep-litellm` is Ready, the backend has rolled, and the
retained provider points to LiteLLM. An explicitly requested test workflow
should appear in LiteLLM/Langfuse; provider presence alone does not prove a
successful generation. A Git revert restores the previous provider connection.

A synthetic request against the currently deployed LiteLLM
`/v1/completions` returned HTTP 200 for `qwen3.8-27b`, text `OK.`, and usage
counts. This verifies route/model compatibility, not the pending Keep rollout
or complete tracing delivery. The pinned provider's environment substitution,
Bearer header, and appended request path were also checked with a mock transport.

Sources: [environment expansion](https://github.com/keephq/keep/blob/v0.52.1/keep/parser/parser.py),
[startup provider updates](https://github.com/keephq/keep/blob/v0.52.1/keep/providers/providers_service.py),
[vLLM URL and authorization behavior](https://github.com/keephq/keep/blob/v0.52.1/keep/providers/vllm_provider/vllm_provider.py).

## Database restart and misleading HTTP 401

The September 8 live inspection traced three rejected Alertmanager deliveries
into Keep's `NoAuthVerifier.get_api_key` lookup: stale PostgreSQL connections
raised `OperationalError`, which Keep 0.52.1 translated into HTTP 401. The
placeholder credential was present and valid for the configured NOAUTH mode.
The live `KEEP_DB_PRE_PING_ENABLED` setting was false, and `/healthcheck`
unconditionally returned 200 while database queries failed.

The Git repair enables connection validation on checkout and replaces only
readiness with [a bounded HTTP plus read-only SQL probe](scripts/readiness.py).
Liveness remains the HTTP worker check, so a database outage withdraws the
backend from its Service without continuously restarting it. The probe uses
the existing database Secret and never prints connection errors. The backend
namespace patch lets Kustomize bind the generated ConfigMap's hash-suffixed
name into the chart's otherwise unnamespaced Deployment.

After Argo sync, with read access to the `keep` namespace:

```sh
kubectl -n keep rollout status deployment/keep-backend --timeout=180s
kubectl -n keep exec deployment/keep-backend -c keep -- python /opt/keep-health/readiness.py
```

Both commands should succeed. Check that normal Alertmanager deliveries arrive
and that `increase(alertmanager_notifications_failed_total{integration="webhook"}[15m])`
is zero after the rollout window. A probe success is not an end-to-end delivery
test. During the next planned database restart, verify the backend temporarily
loses readiness and recovers without a trail of stale-connection 401 responses.
Do not restart the production database just to test this change.

Connection validation repairs stale pooled connections; it cannot guarantee a
request survives a database failure during the request or before readiness
withdraws the endpoint. Keep's upstream exception classification remains a
limitation. The new delivery-failure alert is also visible directly in
Prometheus/Grafana because its own receiver can be unavailable. Roll back by
reverting this change through a PR; this restores the shallow readiness check
and its original failure exposure.

Sources: [Keep connection configuration](https://github.com/keephq/keep/blob/v0.52.1/keep/api/core/db_utils.py),
[NOAUTH verifier](https://github.com/keephq/keep/blob/v0.52.1/keep/identitymanager/identity_managers/noauth/noauth_authverifier.py),
[authentication exception handling](https://github.com/keephq/keep/blob/v0.52.1/keep/identitymanager/authverifierbase.py),
[SQLAlchemy connection validation and limits](https://docs.sqlalchemy.org/en/20/core/pooling.html#disconnect-handling-pessimistic).
