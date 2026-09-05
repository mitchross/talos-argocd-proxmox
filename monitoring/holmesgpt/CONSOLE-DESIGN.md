# Ask the cluster console — source-only draft

**Status: not deployed.** This PR adds the adapter, static UI, and offline tests
only. It does not change Kustomization resources, Helm values, replicas, routes,
RBAC, Cilium policies, Keep workflows, or the inference engine. Holmes remains
in its existing desired state. The deployment write was blocked by the editing
tool; activation is not included or claimed here.

## Intended experience

Open an internal console, ask "Why is radar-ng slow?", select a namespace/time
window, and read an evidence-backed explanation rather than navigating a maze
of dashboards. Holmes gathers the evidence using Kubernetes, Prometheus, Loki
and Tempo, and the existing local llama.cpp model reasons over it.

This source is a thin standard-library Python adapter, not a new investigation
engine. There is no new database, queue service, dependency installation, shell
execution, Kubernetes credential, cloud fallback, or automatic remediation in
the adapter. Its fixed upstream API is Holmes 0.40.0 `/api/chat`, using the
existing `local-qwen` model entry. It lists the actual tools returned by Holmes;
the conclusion is still an AI hypothesis and must identify uncertainty.

## Implemented source behavior

- One console investigation at a time; no automatic retries.
- Asynchronous submit/poll UI; output and tool descriptions displayed as text,
  never executable HTML. Question/time-window/namespace validation is server-side.
- Bounded result size/count, no prompt logging or browser history persistence,
  and results retrievable for 15 minutes in memory only.
- Fixed Host checks, same-origin JSON, CSRF tokens, no arbitrary proxy endpoints,
  no redirects, no CORS, and restrictive response security headers.
- Network failures fail closed: an uncertain upstream completion prevents another
  job being admitted. A lost HTTP connection is not proof GPU work has stopped.

These are NOT user authentication. Any eventual exposed console must be explicitly
limited to trusted LAN/VPN users or placed behind real authentication. Even
read-only cluster logs/configuration can be sensitive.

## Offline tests

```sh
python -m unittest discover -s monitoring/holmesgpt/tests -p test_console.py -v
node --check monitoring/holmesgpt/ui/app.js
```

The 14 tests use a mock Holmes function and a loopback HTTP server. They prove
adapter behavior, not model tool-calling quality, effective cluster permissions,
connectivity, or a working rollout. No Kubernetes API is contacted.

## Activation prerequisites, not changes in this PR

Activation still requires a separately reviewed deployment/route/ConfigMap wiring,
read-only Holmes RBAC and tool configuration, current llama.cpp endpoint and
context/output/step budgets, and a tested network boundary. The broader existing
cluster allow policy must not negate the intended Holmes restrictions. Preserve
raw Alertmanager delivery and prevent an alert storm bypassing on-demand limits.

Review whether authentication is required for the actual audience. Verify cold
start without external model/tokenizer downloads and a real evidence-gathering
question before calling this useful. Other applications share the GPU; the
console is not a GPU scheduler or global rate limiter.

A restart loses in-memory jobs. If a request times out, verify/stop its upstream
work before restarting the adapter and admitting another investigation. A future
multi-replica adapter would need a shared concurrency/state design; this code is
intentionally single-process/single-replica.

Because nothing deploys from these files yet, reverting the source-only PR has
no runtime or storage effect.
