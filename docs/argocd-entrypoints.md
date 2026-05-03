# Argo CD Entrypoints

This is the review map for everything directly rendered by the root Application from `infrastructure/controllers/argocd/apps/`.

`root.yaml` is the manual seed and is not self-managed. After it exists, Argo CD manages this entrypoint tree, including file moves inside `apps/`, ApplicationSet edits, and AppProject edits.

## Layout

| Folder | Purpose |
|--------|---------|
| `bootstrap/` | Wave 0 foundation apps required before the rest of GitOps can converge |
| `core-dependencies/` | Storage, restore, and policy services that later apps depend on |
| `custom-entrypoints/` | Intentional standalone apps kept out of AppSets for ordering or render behavior |
| `appsets/` | Broad directory discovery for infrastructure, databases, monitoring, and user apps |

## Entrypoint Table

| Entrypoint | Type | Wave | Reason | Can move to AppSet? |
|------------|------|------|--------|---------------------|
| `projects.yaml` | AppProjects | 0 | Project grouping and homelab trust boundary | No, foundational Argo CD config |
| `bootstrap/argocd.yaml` | Application | 0 | Self-manages the Argo CD Helm chart and values | No, self-management entrypoint |
| `bootstrap/cilium-app.yaml` | Application | 0 | CNI and Gateway API foundation | No, must be healthy before pods and routes |
| `bootstrap/1passwordconnect.yaml` | Application | 0 | Secret backend for External Secrets | No, secret dependency for later waves |
| `bootstrap/external-secrets.yaml` | Application | 0 | ExternalSecret CRDs and controller | No, CRDs are required by downstream apps |
| `core-dependencies/longhorn-app.yaml` | Application | 1 | Storage foundation before PVC consumers | No, required before restore/app PVC flows |
| `core-dependencies/snapshot-controller-app.yaml` | Application | 1 | VolumeSnapshot CRDs and controller | No, required by backup/restore flows |
| `core-dependencies/volsync-app.yaml` | Application | 1 | Backup/restore engine | No, required before PVC Plumber and restore policies |
| `core-dependencies/pvc-plumber-app.yaml` | Application | 2 | Backup existence API used by Kyverno | No, Kyverno calls this service |
| `core-dependencies/kyverno-app.yaml` | Application | 3 | Policy webhooks must be ready before app PVCs | No, webhook readiness gates later apps |
| `custom-entrypoints/cnpg-barman-plugin-app.yaml` | Application | 3 | CNPG clusters reference the plugin in wave 4 | Not now, dependency must precede database AppSet |
| `custom-entrypoints/keda-app.yaml` | Application | 4 | Standalone after prior AppSet generator/render-cache loop | Maybe, after proving AppSet render stability |
| `custom-entrypoints/temporal-worker-controller-app.yaml` | Application | 4 | Same AppSet render-cache history as KEDA | Maybe, after proving AppSet render stability |
| `custom-entrypoints/opentelemetry-operator-app.yaml` | Application | 5 | Needs cert-manager from wave 4 for webhooks | Maybe, if cert-manager dependency is otherwise enforced |
| `appsets/infrastructure-appset.yaml` | ApplicationSet | 4 | Explicit list of core infrastructure directories | N/A |
| `appsets/database-appset.yaml` | ApplicationSet | 4 | Discovers `infrastructure/database/*/*`; uses `selfHeal: false` for DR | N/A |
| `appsets/monitoring-appset.yaml` | ApplicationSet | 5 | Discovers `monitoring/*` after core infra | N/A |
| `appsets/my-apps-appset.yaml` | ApplicationSet | 6 | Discovers `my-apps/*/*` after storage, policy, and monitoring foundations | N/A |

## Notes

- `project-nomad` is intentionally managed by `appsets/my-apps-appset.yaml` as a single bundled app at `my-apps/home/project-nomad`. Its child folders are resources inside that app, not generated Argo CD Applications.
- Global ignore rules for HTTPRoute, ExternalSecret, and PVC restore fields live in `infrastructure/controllers/argocd/values.yaml`; AppSets should only carry app-specific ignore rules.
- AppProjects are intentionally permissive for a single-operator homelab. They are labels and UI grouping, not hard tenant guardrails.

## Project Nomad App Boundary

Project Nomad is not special to Argo CD; it is special only in repo shape. The `my-apps` ApplicationSet discovers app directories with `my-apps/*/*`, so `my-apps/home/project-nomad` is the generated Application boundary.

Inside that directory there is one parent `kustomization.yaml`. Subdirectories such as `mysql/`, `redis/`, `qdrant/`, `embeddings/`, `kiwix/`, `protomaps/`, `cyberchef/`, and `flatnotes/` are resource folders referenced by the parent kustomization, not independent app directories.

Do not exclude `my-apps/home/project-nomad/*`; that pattern targets child folders the AppSet does not generate. If Project Nomad should ever become multiple Argo CD Applications, add child `kustomization.yaml` files deliberately and update the generator/validation model at the same time.
