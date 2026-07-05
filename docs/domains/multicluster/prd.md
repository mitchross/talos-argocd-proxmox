# PRD: Heterogeneous Multi-Cluster GitOps Fleet (Talos + OpenShift SNO)

> Planning brief, not current cluster truth. Read the live repo and reconcile before acting on any phase.

## What this is

A **two-cluster homelab fleet** used to practice heterogeneous multi-cluster GitOps. The two clusters run *deliberately different* Kubernetes distributions so the exercise mirrors a real multi-cloud fleet (e.g. GKE + ARO): the skill being practiced is managing **per-platform divergence** while keeping **applications portable**. The heterogeneity is the point — do **not** try to make the two clusters identical at the platform layer.

| Cluster | Role | ArgoCD install | CNI | Ingress | Storage | Domain |
|---|---|---|---|---|---|---|
| **Talos** (existing prod) | "GKE-like": you own the platform | Manual Helm (existing) | Cilium | Cilium Gateway API | Longhorn | `*.vanillax.me` |
| **OpenShift SNO** (`sno-ai-lab`) | "ARO-like": opinionated managed | GitOps Operator (OLM) | OVN-Kubernetes | OpenShift Gateway API | LVM Storage | `*.apps.sno-ai-lab.vanillax.xyz` |

### Goals
- Practice hub-of-repos GitOps across clusters, Kustomize base/overlays for app portability, multiple independent ArgoCD instances, OLM/operator-based platform management.
- Keep shared apps portable (write once, adapt per platform via overlays).

### Non-goals (deferred)
- **Control-plane HA** — SNO is single-node by definition.
- **Cross-cluster app/traffic HA** (global LB, cross-cluster failover) — design nothing that blocks it, build nothing for it yet. Stateless Redlib is the eventual first HA target.

## Hard constraints

- **Pure GitOps.** Everything declarative in Git. Only acceptable manual steps are irreducible bootstraps (operator install, 1Password Connect pre-seed), mirroring Talos `scripts/bootstrap-argocd.sh`. **No `argocd cluster add`** or other imperative/UI-only state.
- **Per-cluster, self-managed ArgoCD.** Each cluster runs its own ArgoCD managing its **local** cluster (`https://kubernetes.default.svc`). No remote hub→spoke registration, no cross-cluster ServiceAccount/Secret. (Hub-spoke was explored and rejected.)
- **Shared Git repo** ties the clusters; *what* each runs is selected by the **overlay path** its AppSets scan.
- **Secrets:** single 1Password vault `homelab-prod` via existing ESO + ClusterSecretStore `1password` (refresh 1h, `creationPolicy: Owner`). Never plaintext in Git.
- **Domains:** Talos → `<app>.vanillax.me`; OpenShift → `<app>.apps.sno-ai-lab.vanillax.xyz` (listener hostnames must be subdomains of the cluster ingress domain).
- **Ingress = Gateway API `HTTPRoute` everywhere. No OpenShift Routes for user apps** (console/oauth platform Routes are left alone).
- **AppSet discipline:** cluster-label/directory generators not per-cluster app lists; many purpose-scoped AppSets not one catch-all; **thin generated Applications** (AppSet sets only `path`+`destination`, no `kustomize:`/`helm:` blocks — all config in the overlay so `kustomize build <overlay>` renders standalone); never mix infra with workloads; `HEAD` in `targetRevision`; auto-sync/self-heal on except where DR demands otherwise (preserve CNPG `selfHeal: false`).
- **DNS:** OpenShift `*.apps.sno-ai-lab.vanillax.xyz` served to LAN via Firewalla Custom DNS Rule (`→ 192.168.10.10`, subdomains auto-included); Cloudflare holds grey-cloud A records. Reachable only on-LAN / via VPN — acceptable for a lab.

## Target repository structure

```
<repo-root>/
├── clusters/
│   ├── talos/                 # "GKE-like" — existing setup migrated here intact
│   │   ├── bootstrap/          #   manual Helm ArgoCD install
│   │   ├── infrastructure/  monitoring/
│   │   └── apps/              #   my-apps AppSet(s), repointed
│   └── openshift/            # "ARO-like" — new
│       ├── bootstrap/         #   GitOps Operator Subscription + ArgoCD CR + root
│       ├── infrastructure/    #   Gateway/GatewayClass, cert-manager, ESO+store, LVM
│       └── apps/             #   OpenShift-scoped AppSet(s)
├── apps-shared/<app>/
│   ├── base/                  #   platform-neutral: Deployment, Service, HTTPRoute (empty parentRefs)
│   └── overlays/{talos,openshift}/   #   parentRefs, hostname, storageClass, SCC deltas
└── docs/
```

### Design principles
1. **Quarantine install-method divergence to `clusters/<name>/bootstrap/` only.** Everything above bootstrap is install-method-agnostic, so a future platform pivot is additive/subtractive at the folder level, never a cross-cutting rewrite.
2. **Single-cluster-sane, multi-cluster-ready.** A one-cluster user uses only `clusters/talos/`. Adding cluster N = copy the folder pattern + fill its bootstrap flavor.
3. **Apps shared, platform adapted.** Base holds portable manifests (stable Gateway API v1 `HTTPRoute` fields only — Cilium and OpenShift Gateway API versions differ). Overlays carry the only per-platform deltas: `parentRefs`, hostname, `storageClassName`, `securityContext`/SCC.

## Phased milestones

Execute in order; read the live repo at the start of each phase and confirm acceptance with the human before proceeding.

### Phase 1 — OpenShift bootstrap
Build `clusters/openshift/bootstrap/`:
- OLM `Subscription` for `openshift-gitops-operator` (channel `latest`, `source: redhat-operators`) + `OperatorGroup`. Set `DISABLE_DEFAULT_ARGOCD_INSTANCE: "true"` and `ARGOCD_CLUSTER_CONFIG_NAMESPACES: "argocd"` (scoped cluster-config rights, not cluster-admin).
- Dedicated `ArgoCD` CR in namespace `argocd`: the "wait for child Application" health check plus a new OLM `Subscription` health check (so waves wait for operators to reach `AtLatestKnown`); server-side diff, sync/retry params translated from Talos values; a Route/Gateway for the UI; `SkipDryRunOnMissingResource=true` where apps install CRDs via OLM.
- `root.yaml` → `clusters/openshift/apps/`; a short `bootstrap/README.md` (applied manually once via `oc apply -k`, then self-manages).

**Verify before writing:** the exact `ArgoCD` CR field for resource/health customizations on the *installed* operator version (has drifted across `spec.resourceCustomizations` / `spec.extraConfig` / `spec.resourceHealthChecks`). Also: cluster is **OpenShift 4.22 (RC)** — GitOps-operator support matrix may not list it yet; `latest` should install but is the first suspect if the Subscription stalls.

**Acceptance:** operator installed; dedicated `argocd` instance Running and reachable; default instance NOT created; root app syncs.

### Phase 2 — OpenShift platform infrastructure
`clusters/openshift/infrastructure/`:
- **Gateway API:** `GatewayClass` (controller `openshift.io/gateway-controller/v1`) + `Gateway` in `openshift-ingress`, HTTPS listener on `*.apps.sno-ai-lab.vanillax.xyz`.
- **cert-manager** (OLM) + Cloudflare DNS-01 `ClusterIssuer`/`Certificate` (token from 1Password via ESO) minting the wildcard cert. DNS-01 since no public inbound.
- **ESO + ClusterSecretStore `1password`** (Connect pre-seeded once, then GitOps).
- **LVM Storage operator** + `LVMCluster` on `nvme1n1` → default SC `lvms-vg1`.

**Acceptance:** Gateway `Programmed=True`; cert issued; `lvms-vg1` default; ESO store healthy.

### Phase 3 — First shared app: Redlib
Stateless, no DB/PVC — isolates the ingress/Gateway portability lesson.
- `base/`: Deployment (`quay.io/redlib/redlib:latest`, port 8080), Service, `HTTPRoute` (empty `parentRefs`). Bake OpenShift-friendly `securityContext` (runAsNonRoot, drop ALL caps, seccomp RuntimeDefault, **no hardcoded runAsUser/fsGroup** — let SCC assign).
- `overlays/{talos,openshift}/`: patch `parentRefs`, hostname (`.me` / `.xyz`), namespace.
- Create the OpenShift apps AppSet (directory generator over `apps-shared/*/overlays/openshift`) in an isolated AppProject with Gateway-API `ignoreDifferences`. Optionally add an **additive** Talos AppSet — do NOT modify the live `my-apps/*/*` generator here.

**Acceptance:** Redlib reachable at both hostnames; only per-overlay diff is `parentRefs`+hostname.

### Phase 4 — Talos migration into `clusters/talos/`
Move existing root-level trees (`infrastructure/`, `my-apps/`, `monitoring/`, bootstrap) under `clusters/talos/`; repoint `root.yaml` and all AppSet generator paths.

**Critical gate:** rendered Applications must be **identical** (same names/namespaces/destinations) before vs after, so ArgoCD *adopts* existing resources rather than recreating them → zero workload churn. Validate with `argocd appset generate` / dry diff on a branch before merge. This is the highest-risk step (touches ~200 live apps); it is deferrable if the OpenShift side isn't fully proven yet.

**Acceptance:** branch shows identical generated Applications; live cluster reconciles with no unexpected recreations after merge.

### Phase 5 — Second app (stateful) + backup replication
A single-PVC (maybe CNPG) app: where the hard cross-platform lessons land — `storageClassName` overlay, **SCC friction** (the big one; many upstream images need securityContext adjustment on OpenShift), CNPG on the spoke, and replicating the backup/restore pattern.

**Read the live repo for the current backup design.** Backups are now **kopiur** (Kopia-native, per-PVC `kopiur-backup` component + `dataSourceRef` → `Restore`). Kyverno, pvc-plumber, and VolSync are **retired** — do not port them. Port the current kopiur pattern to OpenShift, replicating to the same TrueNAS/RustFS target. CNPG stays native Barman/S3.

**Acceptance:** stateful app runs on both clusters; correct SC per platform; SCC resolved via overlay; backups land on the shared target.

### Phase 6 — Specialize OpenShift (GPU + AI, future)
`sno-ai-lab` is GPU-purposed:
- **GPU stack:** NFD → verify `feature.node.kubernetes.io/pci-10de.present` → NVIDIA GPU Operator `ClusterPolicy`. Current card is a GTX 1050 Ti (Pascal, unsupported-but-works); owner plans RTX 3090(s) (Ampere, smooth) — validate against those. Multi-GPU: node reports `nvidia.com/gpu: "N"`.
- **OpenShift Virtualization** (installed) for GPU-passthrough VMs (needs IOMMU in BIOS).
- **OpenShift AI** + Gateway API Inference Extensions for model serving.

Decide per use: GPU for containers (NFD→Operator→ClusterPolicy) vs VM passthrough (HyperConverged/IOMMU). Ask the human.

**Acceptance:** (with 3090s in) node reports `nvidia.com/gpu`; a test CUDA workload or VM consumes a GPU.

## Open questions to resolve against the live repo
1. Exact `ArgoCD` CR schema field for health checks on the installed operator version.
2. Current kopiur backup/restore design (Phase 5) — confirm the per-PVC component + `Restore` `dataSourceRef` pattern before porting.
3. Exact AppSet generator syntax in use (path templating; namespace derivation — convention is `{{path.basename}}`; deeper overlay paths may need a different segment).
4. Whether to run Phase 4 now or after the OpenShift side is proven.
5. Exact Cilium Gateway name/namespace/listener for the Talos overlay `parentRefs`.
6. Redlib's current manifests if it already exists in `my-apps/` — refactor those (preserve env/limits/labels).

## Working style
- Read the live repo first each phase; reconcile with this brief; surface conflicts and ask focused questions before any destructive/structural change.
- Small reviewable commits on a branch; validate (`kustomize build`, `argocd appset generate`, dry diffs) before applying.
- Preserve existing conventions (sync waves, `ignoreDifferences`, selfHeal exceptions, ESO patterns) unless explicitly changing them.
- Keep install-method divergence quarantined in `bootstrap/`; everything else portable.
