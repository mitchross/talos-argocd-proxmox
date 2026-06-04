# temporal — server (cluster side)

Self-hosted Temporal server for the cluster. This directory deploys the
**server**; application workers (e.g. `news-reader-temporal-worker`,
`radar-ng`'s temporal worker) live in their own sibling dirs and connect
in via `TemporalConnection` CRs from the
[Temporal Worker Controller](../../../manifests/infra/temporal-worker-controller/).

Read this *with* `news-reader/temporal/README.md` (in the news-reader
repo) — together they cover server side + app side of the same system.

---

## What this dir deploys

```mermaid
flowchart LR
    subgraph chart[Helm chart go.temporal.io/helm-charts@1.2.0]
        FE[frontend<br/>:7233 gRPC]
        HIST[history]
        MATCH[matching]
        IWK[server-worker<br/>internal]
        WEB[temporal-web<br/>UI]
        ADM[admintools]
        JOB[schema-job<br/>argo sync-wave -1]
    end

    CNPG[(CloudNative-PG<br/>cluster: temporal-database<br/>db: temporal + temporal_visibility)]
    SECRET[externalsecret<br/>temporal-db-secret]
    HR[HTTPRoute<br/>temporal.vanillax.me]

    JOB -- "manageSchema migrations" --> CNPG
    FE -- writes --> HIST
    FE -- enqueues --> MATCH
    HIST <-- reads/writes --> CNPG
    MATCH <-- reads --> CNPG
    SECRET --> FE
    SECRET --> HIST
    SECRET --> MATCH
    SECRET --> IWK
    SECRET --> JOB
    WEB -- gRPC --> FE
    HR --> WEB
```

| Component   | Role |
|-------------|------|
| `frontend`  | gRPC API the SDKs and `temporal` CLI talk to (port 7233). |
| `history`   | Owns workflow history. Replays/persists events to PG. |
| `matching`  | Owns task queues; long-poll endpoint workers connect to. |
| `worker`    | **Internal** server worker — runs Temporal's own background workflows (archival, retention, schedule trigger). Distinct from *your* application workers. |
| `web`       | UI at `temporal.vanillax.me`. |
| `admintools`| Side-pod with `tctl` / `temporal` CLI shells out to. Handy via `kubectl exec`. |
| schema Job  | Runs `temporal-sql-tool` migrations against PG before pods boot. |

---

## Files

```
kustomization.yaml      # Helm chart inflation + JSON patches for ArgoCD sync waves
values.yaml             # Helm values: image pin, persistence (PG), resources
namespace.yaml          # `temporal` namespace
namespace-init-job.yaml # Post-install Job — creates the `default` Temporal namespace
externalsecret.yaml     # Pulls Postgres creds from 1Password into `temporal-db-secret`
httproute.yaml          # Gateway API route: temporal.vanillax.me → temporal-web
scripts/
  seed-namespaces.sh    # Mounted by namespace-init-job; idempotent `tctl namespace register`
charts/temporal-1.1.1/  # Vendored chart for review/diff (kustomize inflates fresh from `helm`)
```

---

## How the bring-up sequence works

ArgoCD applies this app in sync-wave order. The critical part: SQL schema
migrations **must run before any temporal server Pod boots**, otherwise
`history` panics with "schema mismatch."

```mermaid
sequenceDiagram
    autonumber
    participant Argo as ArgoCD
    participant CNPG as CloudNative-PG
    participant Job as schema-job<br/>(sync-wave -1)
    participant Server as temporal-{frontend,history,matching,worker}
    participant Seed as namespace-init-job<br/>(PostSync)
    participant CLI as tctl seed-namespaces.sh

    Argo->>CNPG: already running (separate App, manifests/database/cloudnative-pg/temporal)
    Argo->>Job: Sync wave -1 — apply schema-job
    Job->>CNPG: temporal-sql-tool setup-schema + update-schema
    CNPG-->>Job: done
    Argo->>Server: Sync wave 0 — apply Deployments
    Server->>CNPG: gRPC startup → schema check passes
    Argo->>Seed: PostSync — namespace-init-job
    Seed->>CLI: seed-namespaces.sh
    CLI->>Server: `temporal operator namespace create default`
```

The JSON patch in `kustomization.yaml` is what makes this work:

```yaml
patches:
  - target: {kind: Job, labelSelector: helm.sh/chart}  # only the chart's Jobs
    patch: |
      - op: add
        path: /metadata/annotations/argocd.argoproj.io~1hook
        value: Sync
      - op: add
        path: /metadata/annotations/argocd.argoproj.io~1sync-wave
        value: "-1"
      - op: add
        path: /metadata/annotations/argocd.argoproj.io~1hook-delete-policy
        value: BeforeHookCreation
```

The selector is intentional — without it, the patch would also stomp our
own `temporal-namespace-seed` Job (the `PostSync` namespace creator) and
turn it into a pre-sync wave, which would deadlock because the seed Job
needs the server up.

---

## Persistence: why CloudNative-PG (not the chart's bundled DB)

The Temporal Helm chart's defaults were trimmed of bundled subcharts in
1.x (no Cassandra, no Prometheus, no PG). We point at our own
`CloudNativePG` cluster:

```yaml
# excerpt from values.yaml
server:
  config:
    persistence:
      defaultStore: default
      visibilityStore: visibility
      datastores:
        default:    {sql: {databaseName: temporal,            connectAddr: temporal-database-rw.cloudnative-pg.svc.cluster.local:5432, ...}}
        visibility: {sql: {databaseName: temporal_visibility, connectAddr: temporal-database-rw.cloudnative-pg.svc.cluster.local:5432, ...}}
```

The `temporal-database` CNPG cluster (operator at
`manifests/database/cloudnative-pg/`) gives us automated backups,
HA-ready PG, and a `-rw` Service that resolves to whichever Pod is
currently primary. Two databases — one for workflow history, one for
visibility (searchable workflow attributes).

> 💡 **`numHistoryShards: 1`** is set in our values.yaml. This is
> **permanent** — it can never be lowered, and raising it requires
> re-creating the namespace. Production clusters typically use 512+;
> 1 is fine for a homelab single-node, single-namespace setup.

---

## Versions & upgrades

```yaml
# kustomization.yaml (excerpt)
helmCharts:
  - name: temporal
    repo: https://go.temporal.io/helm-charts
    version: 1.2.0          # chart version — renovate auto-bumps via .github/renovate.json5
    valuesFile: values.yaml

# values.yaml (excerpt)
server:
  image:
    repository: temporalio/server
    tag: 1.31.0             # server version override — chart's default lags real releases
```

The **chart** and the **server image** rev independently. The chart
controls Helm templates (Deployments/Services/etc.); the image tag
controls the actual `temporalio/server` binary. The chart's bundled
default often lags Temporal's release cadence, so we pin the image
explicitly.

When bumping the server image:
1. Read [Temporal server release notes](https://github.com/temporalio/temporal/releases).
2. If the bump crosses a schema migration boundary, the schema Job will
   run automatically (sync-wave -1). Watch its logs the first time.

---

## Web UI

```
https://temporal.vanillax.me   (Cloudflare tunnel → Cilium gateway-external)
```

The HTTPRoute in `httproute.yaml` is what gets you there. UI is
unauthenticated today — if you ever expose it externally to multiple
people, gate it via Cloudflare Access on the tunnel.

For purely local access:
```bash
kubectl -n temporal port-forward svc/temporal-web 8080:8080
# open http://localhost:8080
```

---

## Server vs Worker Controller — two operator-style pieces

Important distinction (this confuses everyone the first time):

| Thing | Where | What it manages |
|---|---|---|
| **Temporal server** | `manifests/apps/development/temporal/` (this dir) | The server itself — frontend, history, matching, web, server-worker. Deployed via the official Helm chart. |
| **Temporal Worker Controller** | `manifests/infra/temporal-worker-controller/` | A *Kubernetes controller* (CRD-based). Watches your `TemporalWorkerDeployment` CRs and turns each into a versioned `apps/v1 Deployment`. Handles Worker Versioning rollouts. |

You can run the server without the worker controller — workers would
just be plain Deployments and you'd lose progressive rollouts. We use
both because Worker Versioning is the whole point.

---

## Per-application workers in this cluster

| App | Path |
|---|---|
| `news-reader-temporal-worker` (news-digest task queue) | `manifests/apps/development/news-reader-temporal-worker/` |
| `radar-ng` workers | `manifests/apps/development/radar-ng/temporal-worker-deployment.yaml` |

Each ships its own `TemporalConnection` CR pointing at
`temporal-frontend.temporal.svc.cluster.local:7233` and its own
`TemporalWorkerDeployment` CR. They're independent Apps in ArgoCD.

---

## Operations cheatsheet

```bash
# Check server is healthy
kubectl -n temporal get pods
kubectl -n temporal logs deploy/temporal-frontend --tail=50

# Open a tctl shell inside the cluster (admintools sidecar)
kubectl -n temporal exec -it deploy/temporal-admintools -- bash
# now you can run `temporal workflow list ...`, etc.

# Force ArgoCD resync (e.g. after editing values.yaml)
argocd app sync temporal

# Check schema migration logs
kubectl -n temporal logs job/temporal-schema-1.x.y

# Watch the namespace-init job (first install only)
kubectl -n temporal logs job/temporal-namespace-seed
```

---

## Further reading

- [Tips for running Temporal on Kubernetes](https://temporal.io/blog/tips-for-running-temporal-on-kubernetes) — the article this setup follows
- [Temporal Helm chart](https://github.com/temporalio/helm-charts)
- [Temporal Worker Controller](https://github.com/temporalio/temporal-worker-controller)
- [news-reader temporal worker README](https://gitea.vanillax.me/vanillax/news-reader/src/branch/main/temporal/README.md) — application side of the same system, full worker-versioning walkthrough
