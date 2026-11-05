# PRD: heterogeneous multi-cluster GitOps fleet (Talos + OpenShift SNO)

> Planning brief, not current cluster truth. Read the live repo and reconcile it with this brief before acting on any phase.

The [enterprise multi-cluster GitOps roadmap](enterprise-gitops-roadmap.md) is
the strategic source of truth for adoption triggers, safety constraints, and
incremental controls. This PRD applies those rules to one Talos plus
OpenShift fleet. It does not override them.

## What this is

A two-cluster homelab fleet for practicing heterogeneous multi-cluster GitOps. The two clusters run deliberately different Kubernetes distributions, like a real multi-cloud fleet (for example GKE + ARO). The skill to practice is managing per-platform divergence while keeping applications portable. The difference is the point. **Do not make the two clusters identical at the platform layer.**

| Cluster | Role | ArgoCD install | CNI | Ingress | Storage | Domain |
|---|---|---|---|---|---|---|
| **Talos** (existing cluster) | "GKE-like": you own the platform | Manual Helm (existing) | Cilium | Cilium Gateway API | Longhorn | `*.vanillax.me` |
| **OpenShift SNO** (`sno-ai-lab`) | "ARO-like": opinionated managed | GitOps Operator (OLM) | OVN-Kubernetes | OpenShift Gateway API | LVM Storage | `*.apps.sno-ai-lab.vanillax.xyz` |

### Goals
- Practice hub-of-repos GitOps across clusters, Kustomize base/overlays for app portability, multiple independent ArgoCD instances, OLM/operator-based platform management.
- Keep shared apps portable (write once, adapt per platform via overlays).

### Non-goals (deferred)
- **Control-plane HA.** SNO is single-node by definition.
- **Cross-cluster app/traffic HA** (global LB, cross-cluster failover). Design nothing that blocks it. Build nothing for it yet. Stateless Redlib is the eventual first HA target.

## Hard constraints

- **Pure GitOps.** Everything is declarative in Git. The only acceptable manual steps are irreducible bootstraps (operator install, 1Password Connect pre-seed), as in Talos `scripts/bootstrap-argocd.sh`. **No `argocd cluster add`** or other imperative or UI-only state.
- **Per-cluster, self-managed ArgoCD.** Each cluster runs its own ArgoCD, which manages its local cluster (`https://kubernetes.default.svc`). There is no remote hub-to-spoke registration and no cross-cluster ServiceAccount or Secret. Hub-spoke was explored and rejected.
- **Shared Git repo.** One repo ties the clusters together. The overlay path that a cluster's AppSets scan selects what that cluster runs.
- **Secrets.** One 1Password vault `homelab-prod`, through the existing ESO + ClusterSecretStore `1password` (refresh 1h, `creationPolicy: Owner`). Never plaintext in Git.
- **Domains.** Talos uses `<app>.vanillax.me`. OpenShift uses `<app>.apps.sno-ai-lab.vanillax.xyz`. Listener hostnames must be subdomains of the cluster ingress domain.
- **Ingress is Gateway API `HTTPRoute` everywhere. No OpenShift Routes for user apps.** Leave the console and oauth platform Routes alone.
- **AppSet discipline.** Use cluster-label or directory generators, not per-cluster app lists. Use many purpose-scoped AppSets, not one catch-all. Keep generated Applications thin: the AppSet sets only `path` and `destination`, with no `kustomize:` or `helm:` blocks. Put all config in the overlay so `kustomize build <overlay>` renders standalone. Never mix infra with workloads. Use `main` in `targetRevision`, matching the current repository. Turn auto-sync and self-heal on everywhere. The old CNPG restore-transaction gates were retired with CNPG on 2026-08-13.
- **DNS.** A Firewalla Custom DNS Rule serves OpenShift `*.apps.sno-ai-lab.vanillax.xyz` to the LAN (`→ 192.168.10.10`, subdomains auto-included). Cloudflare holds grey-cloud A records. The apps are reachable only on the LAN or over VPN, which is acceptable for a lab.

## Target repository structure

```
<repo-root>/
├── infrastructure/            # existing Talos platform; remains in place
├── monitoring/                # existing Talos observability; remains in place
├── my-apps/                   # existing Talos apps; remains in place
├── clusters/
│   └── openshift/             # new cluster-specific platform configuration
│       ├── bootstrap/         # GitOps Operator Subscription + ArgoCD CR + root
│       ├── infrastructure/    # Gateway/GatewayClass, cert-manager, ESO+store, LVM
│       └── apps/              # OpenShift-scoped AppSet(s)
├── apps-shared/<app>/
│   ├── base/                  #   platform-neutral: Deployment, Service, HTTPRoute (empty parentRefs)
│   └── overlays/{talos,openshift}/   #   parentRefs, hostname, storageClass, SCC deltas
├── deploy-targets/            # add only when explicit target descriptors are needed
│   ├── talos/
│   └── openshift/
└── docs/
```

### Design principles
1. **Add the second cluster without relocating the first.** Existing Talos entrypoints and generated Application identities stay unchanged. A future layout migration needs a separate demonstrated benefit and an identity-preserving dry diff.
2. **Confine new install-method divergence to `clusters/<name>/bootstrap/`.** Cluster-specific platform configuration stays under that cluster. Portable applications live under `apps-shared/` only after they have a second consumer.
3. **Apps shared, platform adapted.** Base holds portable manifests. Use stable Gateway API v1 `HTTPRoute` fields only, because Cilium and OpenShift Gateway API versions differ. Overlays carry the only per-platform deltas: `parentRefs`, hostname, `storageClassName`, `securityContext`/SCC.

## Phased milestones

Execute in order. Read the live repo at the start of each phase. Confirm acceptance with the human before proceeding.

### Phase 1: OpenShift bootstrap
Build `clusters/openshift/bootstrap/`:
- OLM `Subscription` for `openshift-gitops-operator` (channel `latest`, `source: redhat-operators`) + `OperatorGroup`. Set `DISABLE_DEFAULT_ARGOCD_INSTANCE: "true"` and `ARGOCD_CLUSTER_CONFIG_NAMESPACES: "argocd"`. These give scoped cluster-config rights, not cluster-admin.
- Dedicated `ArgoCD` CR in namespace `argocd`, with:
  - the "wait for child Application" health check, plus a new OLM `Subscription` health check so waves wait for operators to reach `AtLatestKnown`
  - server-side diff, and sync and retry params translated from Talos values
  - a Route or Gateway for the UI
  - `SkipDryRunOnMissingResource=true` where apps install CRDs through OLM
- `root.yaml` pointing at `clusters/openshift/apps/`, and a short `bootstrap/README.md`. Apply the bootstrap manually once with `oc apply -k`. After that it manages itself.

**Verify before writing:** the exact `ArgoCD` CR field for resource and health customizations on the installed operator version. It has drifted across `spec.resourceCustomizations`, `spec.extraConfig` and `spec.resourceHealthChecks`. The original planning snapshot recorded **OpenShift 4.22 RC**; confirm the installed version, supported GitOps Operator channel, and support matrix instead of treating that snapshot or the `latest` channel as current truth.

**Acceptance:** operator installed; dedicated `argocd` instance Running and reachable; default instance NOT created; root app syncs.

### Phase 2: OpenShift platform infrastructure
`clusters/openshift/infrastructure/`:
- **Gateway API.** `GatewayClass` (controller `openshift.io/gateway-controller/v1`) + `Gateway` in `openshift-ingress`, HTTPS listener on `*.apps.sno-ai-lab.vanillax.xyz`.
- **cert-manager** (OLM) + Cloudflare DNS-01 `ClusterIssuer`/`Certificate` (token from 1Password via ESO) minting the wildcard cert. Use DNS-01 because there is no public inbound.
- **ESO + ClusterSecretStore `1password`** (Connect pre-seeded once, then GitOps).
- **LVM Storage operator** + `LVMCluster` on `nvme1n1`, giving default SC `lvms-vg1`.

**Acceptance:** Gateway `Programmed=True`; cert issued; `lvms-vg1` default; ESO store healthy.

### Phase 3: first shared app, Redlib
Redlib is stateless, with no DB or PVC, so it isolates the ingress and Gateway portability lesson.
- `base/`: Deployment (`quay.io/redlib/redlib:latest`, port 8080), Service, `HTTPRoute` (empty `parentRefs`). Bake in an OpenShift-friendly `securityContext` (runAsNonRoot, drop ALL caps, seccomp RuntimeDefault). **Do not hardcode runAsUser or fsGroup.** Let SCC assign them.
- `overlays/{talos,openshift}/`: patch `parentRefs`, hostname (`.me` / `.xyz`), namespace.
- Create the OpenShift apps AppSet (directory generator over `apps-shared/*/overlays/openshift`) in an isolated AppProject with Gateway-API `ignoreDifferences`. Optionally add an additive Talos AppSet. **Do not modify the live `my-apps/*/*` generator here.**

**Acceptance:** Redlib reachable at both hostnames; only per-overlay diff is `parentRefs`+hostname.

### Phase 4: Talos adoption of the shared-app pattern
Add the Talos overlay for the stateless pilot to a new, purpose-scoped AppSet.
Leave `infrastructure/`, `monitoring/`, `my-apps/`, `root.yaml`, and the existing
AppSets in place. The shared-app AppSet must discover only explicit shared
targets, so it cannot claim an application already owned by `my-apps/*/*`.

**Critical gate:** render the existing and proposed ApplicationSets together and
prove that every Application name and managed-resource owner is unique. If the
pilot already exists under `my-apps/`, migrate only that pilot with an explicit
adoption plan and before/after dry diff.

**Acceptance:** the pilot reconciles on both clusters, existing Applications are
unchanged, and `FailOnSharedResource=true` reports no ownership collision.

### Phase 5: second app (stateful) + backup replication
Use a single-PVC app (plain Postgres included). The hard cross-platform lessons land here: the `storageClassName` overlay, SCC friction, and replicating the backup/restore pattern. SCC friction is the big one, because many upstream images need a securityContext adjustment on OpenShift.

**Read the live repo for the current backup design.** Backups are now kopiur (Kopia-native, per-PVC `kopiur-backup` component + `dataSourceRef` pointing at a `Restore`). Kyverno, pvc-plumber, and VolSync are retired. **Do not port them.** The clusters may share the TrueNAS/RustFS service only after repository, hostname, username, and source-path identity is cluster-qualified and CI rejects collisions. Databases are plain Postgres + kopiur (CNPG retired 2026-08-13), so they follow the same cluster-qualified identity rule as every other PVC.

**Acceptance:** stateful app runs on both clusters; correct SC per platform; SCC resolved via overlay; each cluster backs up and restores only its own lineage; a test proves that "latest" cannot select the other cluster's snapshot.

### Phase 6: specialize OpenShift (GPU + AI, future)
`sno-ai-lab` is GPU-purposed:
- **GPU stack.** Install NFD, verify `feature.node.kubernetes.io/pci-10de.present`, then create the NVIDIA GPU Operator `ClusterPolicy`. The current card is a GTX 1050 Ti (Pascal, unsupported but works). The owner plans RTX 3090s (Ampere, smooth), so validate against those. With multiple GPUs, the node reports `nvidia.com/gpu: "N"`.
- **OpenShift Virtualization** (installed) for GPU-passthrough VMs. It needs IOMMU in BIOS.
- **OpenShift AI** + Gateway API Inference Extensions for model serving.

Decide per use between GPU for containers (NFD, Operator, ClusterPolicy) and VM passthrough (HyperConverged, IOMMU). Ask the human.

**Acceptance:** with the 3090s in, the node reports `nvidia.com/gpu`; a test CUDA workload or VM consumes a GPU.

## Open questions to resolve against the live repo
1. Exact `ArgoCD` CR schema field for health checks on the installed operator version.
2. Exact cluster-qualified kopiur and Barman identity format for Phase 5.
3. Generator fields for deeper shared-app overlay paths. Current AppSets use strict Go templates such as `{{ .path.basename }}`; do not copy deprecated fasttemplate syntax.
4. Whether the Talos shared-app pilot should follow immediately after OpenShift validation or remain deferred.
5. Exact Cilium Gateway name/namespace/listener for the Talos overlay `parentRefs`.
6. Redlib's current manifests, if it already exists in `my-apps/`. Refactor those and preserve env, limits and labels.

## Working style
- Read the live repo first in each phase. Reconcile it with this brief. Surface conflicts and ask focused questions before any destructive or structural change.
- Make small reviewable commits on a branch. Validate (`kustomize build`, `argocd appset generate`, dry diffs) before applying.
- Keep existing conventions (sync waves, `ignoreDifferences`, selfHeal exceptions, ESO patterns) unless explicitly changing them.
- Keep install-method divergence in `bootstrap/`. Keep everything else portable.

## Resume checklist

When implementation begins again:

- [ ] Read the roadmap, this PRD, and the current repository before proposing changes.
- [ ] List any live-state or repository facts that differ from this planning snapshot.
- [ ] Resolve the installed OpenShift/GitOps versions and remaining open questions.
- [ ] Render the next phase independently and state its expected result and rollback.
- [ ] For shared apps, prove unique Application names and resource ownership.
- [ ] Before any stateful pilot, define and test cluster-qualified kopiur/Barman identities.
