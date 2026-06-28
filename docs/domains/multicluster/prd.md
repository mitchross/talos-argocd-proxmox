# PRD: Heterogeneous Multi-Cluster GitOps Fleet (Talos + OpenShift SNO)

> Captured 2026-06-01 — planning brief, not current cluster truth.

> **For the agent (Claude Code) executing this:** This document is a *brief*, not a literal spec. Many details were reasoned out in a planning conversation **without access to the live repo**, so some assumptions may be stale or wrong. Your **first job in every phase is to read the actual repository state and reconcile it against this PRD.** When the repo contradicts an assumption here, or when you hit a real decision point (naming, placement, a destructive change, an ambiguous convention), **STOP and ask the human a focused question** rather than guessing. Re-prompting is expected and encouraged. Work phase by phase; do not run ahead.

---

## 1. Context & Goals

### What this is
The owner runs (or is building) a **two-cluster homelab fleet** and is using it to **practice multi-cluster / multi-cloud DevOps for work**. The two clusters are *deliberately different Kubernetes distributions* so the exercise mirrors a real heterogeneous fleet (e.g. GKE + ARO), where each "cloud" has its own opinionated way of doing things and the skill is managing the **divergence** while keeping **applications portable**.

### The two clusters and their intentional roles
| Cluster | Role in the simulation | ArgoCD install method | CNI | Ingress | Storage | Domain |
|---|---|---|---|---|---|---|
| **Talos** (existing, production homelab) | "GKE-like": you assemble/own the platform | **Manual Helm install** (existing, untouched) | Cilium | Cilium Gateway API | Longhorn | `*.vanillax.me` |
| **OpenShift SNO** (new, `sno-ai-lab`) | "ARO-like": opinionated managed platform | **OpenShift GitOps Operator (OLM)** | OVN-Kubernetes | OpenShift Gateway API (native) | LVM Storage | `*.apps.sno-ai-lab.vanillax.xyz` |

The **heterogeneity is the point** — do NOT try to make the two clusters identical at the platform layer. The ArgoCD install methods differing (Helm vs Operator) is **intentional**, not drift to fix.

### Goals
- Build fluency in: hub-of-repos GitOps across clusters, Kustomize base/overlays for app portability, multiple independent ArgoCD instances, per-platform divergence handling, OLM/operator-based platform management.
- Keep the **shared apps portable** (write once, adapt per platform via overlays).
- Make the repo a clean, scalable, teaching-quality reference that single-cluster users can still use sanely.

### Explicit non-goals (deferred, do not build now)
- **Control-plane HA** — SNO is single-node by definition; real HA is a later, separate effort (3-node compact OpenShift or multi-node Talos).
- **Cross-cluster application/traffic HA** (global load balancing, health-checked failover of an app across both clusters) — deferred to a later phase. Design nothing that *blocks* it, but build nothing for it yet. Stateless apps (e.g. Redlib) will be the first HA target when that phase comes.

---

## 2. Hard Constraints & Conventions (do not violate)

- **Pure GitOps.** Everything declarative and in Git. The only acceptable manual steps are irreducible trust/inception bootstraps (operator install, 1Password Connect pre-seed) — analogous to the existing Talos `scripts/bootstrap-argocd.sh`. **No `argocd cluster add`** or other imperative/UI-only state (it lands only in etcd, violates GitOps DR). *(ArgoCD anti-pattern.)*
- **Per-cluster, self-managed ArgoCD.** Each cluster runs its own ArgoCD managing its **local** cluster (`https://kubernetes.default.svc`). This matches how the owner already works and is multi-cloud-authentic. **No remote hub→spoke registration, no cross-cluster ServiceAccount/cluster-Secret.** (Earlier planning briefly explored hub-spoke; it was rejected. Ignore any hub-spoke artifacts.)
- **Shared Git repo** ties the clusters together; *what* each cluster runs is selected by the **overlay path** its AppSets scan.
- **Secrets:** single 1Password vault **`homelab-prod`** (vault id 1), via the existing **ESO + ClusterSecretStore named `1password`**. ExternalSecret conventions: `refresh interval 1h`, `creationPolicy: Owner`, field mapping via `spec.data[].secretKey`/`remoteRef.property`. The only acceptable "secret not in Git" is referencing an external source (ESO) — never plaintext in Git.
- **Domains:** Talos apps → `<app>.vanillax.me`; OpenShift apps → `<app>.apps.sno-ai-lab.vanillax.xyz` (OpenShift Gateway listener hostnames **must** be subdomains of the cluster ingress domain `apps.sno-ai-lab.vanillax.xyz`).
- **Ingress = Gateway API `HTTPRoute` everywhere. No OpenShift Routes for user apps.** (The OpenShift console/oauth ride on platform Routes — that's platform-internal, leave it alone.) Gateway API is Red Hat's stated forward direction and the only portable choice across both clusters.
- **AppSet discipline** *(ArgoCD anti-patterns to honor):*
  - Use **cluster labels / directory generators**, not ad-hoc per-cluster app lists.
  - **Many purpose-scoped AppSets**, not one giant catch-all. (Existing repo already does this: infrastructure / monitoring / my-apps.)
  - **Thin generated Applications**: the AppSet sets only `path` + `destination`; **no `kustomize:`/`helm:` override blocks inside the Application** — all config lives in the overlay so `kustomize build <overlay>` renders standalone.
  - **Never mix infrastructure apps with developer workloads** in the same grouping. A new cluster should "come ready" with its platform layer before workloads land.
  - Use **`HEAD`** in `targetRevision`. Promotion/comparison happens at the **overlay** level, never by versioning Application/AppSet manifests.
  - Keep **auto-sync/self-heal on** by default; disable only where DR demands it (e.g. existing CNPG apps use `selfHeal: false` deliberately — preserve such exceptions).
- **DNS:** OpenShift `*.apps.sno-ai-lab.vanillax.xyz` is served to the LAN via a **Firewalla Custom DNS Rule** (`apps.sno-ai-lab.vanillax.xyz` → `192.168.10.10`, subdomains auto-included). Cloudflare holds DNS-only (grey-cloud) A records for the cluster too. Public records point at a private IP, so the cluster is reachable only on-LAN / via VPN — acceptable for a lab.

---

## 3. Target Architecture

### Repository structure (destination state)
```
<repo-root>/
├── clusters/
│   ├── talos/                 # "GKE-like" — existing setup migrated here intact
│   │   ├── bootstrap/          #   manual Helm ArgoCD install (existing scripts/values)
│   │   ├── infrastructure/
│   │   ├── monitoring/
│   │   └── apps/              #   the my-apps AppSet(s), repointed to new paths
│   └── openshift/            # "ARO-like" — new
│       ├── bootstrap/         #   GitOps Operator Subscription + dedicated ArgoCD CR + root
│       ├── infrastructure/    #   Gateway/GatewayClass, cert-manager(OLM), ESO+store, LVM
│       └── apps/             #   OpenShift-scoped AppSet(s)
├── apps-shared/              # workloads deployable to ANY cluster
│   └── <app>/
│       ├── base/              #   platform-neutral: Deployment, Service, HTTPRoute(parentRefs empty)
│       └── overlays/
│           ├── talos/         #   parentRefs→Cilium gateway, .me host, longhorn SC
│           └── openshift/     #   parentRefs→OpenShift gateway, .xyz host, lvms SC, SCC patch
├── docs/
│   ├── multicluster-prd.md    #   THIS FILE
│   └── adding-a-cluster.md    #   runbook: "copy clusters/<x>, swap bootstrap flavor"
└── README.md                 # "one cluster? use clusters/talos. more? add clusters/<name>."
```

### Key design principles (preserve these — they give the structure its value)
1. **Quarantine install-method divergence to `clusters/<name>/bootstrap/` only.** Everything above bootstrap (infrastructure apps, AppSets, overlays) must be **install-method-agnostic** — an ApplicationSet doesn't care whether its ArgoCD was Helm- or Operator-installed. This guarantees a future platform pivot (e.g. drop OpenShift, add GKE+AKS) is *additive/subtractive at the folder level* (`clusters/<name>/` + a new `overlays/<name>/` per app), never a cross-cutting rewrite.
2. **Single-cluster-sane, multi-cluster-ready.** A one-cluster user uses only `clusters/talos/`. Adding cluster N = copy the folder pattern + fill in its bootstrap flavor.
3. **Apps shared, platform adapted.** Base holds the portable manifests (stable Gateway API v1 `HTTPRoute` fields only — no experimental fields, since Cilium's and OpenShift's Gateway API versions differ). Overlays carry the *only* per-platform deltas: `parentRefs` (which Gateway), hostname (`.me`/`.xyz`), `storageClassName`, and `securityContext`/SCC.

### What ports cleanly vs. what is per-platform
| Concern | Talos | OpenShift | Strategy |
|---|---|---|---|
| Ingress | Cilium Gateway API | OpenShift Gateway API | **HTTPRoute in base**, `parentRefs`+hostname in overlay |
| Storage | Longhorn | LVM (`lvms-vg1`) | `storageClassName` overlay patch |
| Secrets | 1Password+ESO | 1Password+ESO | **Ports cleanly** (same vault/store) |
| Backups | kopiur (Kopia → RustFS S3; pvc-plumber/VolSync retired 2026-06-27) | replicate to same TrueNAS NFS | per-PVC `kopiur-backup` component + `dataSourceRef` → `Restore` |
| CNI | Cilium | OVN | platform-owned, NOT GitOps'd from the other cluster |
| Security | permissive | SCCs enforced | `securityContext` overlay patch (don't hardcode UID; let SCC assign) |
| ArgoCD install | Helm (manual) | GitOps Operator (OLM) | **intentionally different**, quarantined in `bootstrap/` |

---

## 4. Phased Milestones (each has acceptance criteria; ask questions before/within each)

> Execute in order. After each phase, confirm acceptance criteria with the human before proceeding. Always read the live repo at the start of a phase to reconcile against this brief.

### Phase 1 — OpenShift bootstrap (the "ARO-like" foundation)
Build `clusters/openshift/bootstrap/`:
- **Operator install:** OLM `Subscription` for `openshift-gitops-operator`, channel `latest`, `source: redhat-operators`, in `openshift-gitops-operator` namespace (+ its `OperatorGroup`). Set `config.env`:
  - `DISABLE_DEFAULT_ARGOCD_INSTANCE: "true"` (do not use the auto-created default instance)
  - `ARGOCD_CLUSTER_CONFIG_NAMESPACES: "argocd"` (grants the dedicated instance scoped cluster-config rights to manage OLM operators — **not** full cluster-admin)
- **Dedicated `ArgoCD` CR** (`argoproj.io/v1alpha1`) named per the human's choice in namespace **`argocd`**, with:
  - Health checks translated from the Talos ArgoCD config: the **"wait for child" Application** health check, **plus a new OLM `Subscription` health check** (so sync waves wait for operators to reach `AtLatestKnown`/installed before dependents sync).
  - Server-side diff, sync options, retry/perf params translated from the existing Talos values.
  - A `Route` (or Gateway) for the ArgoCD UI.
  - **Add the `SkipDryRunOnMissingResource=true` sync option** where apps install CRDs via OLM asynchronously.
- **Root app** (`root.yaml`) → points at `clusters/openshift/apps/`.
- A short `bootstrap/README.md`: this tree is applied **manually once** (`oc apply -k clusters/openshift/bootstrap/`, mirroring the Talos bootstrap script); then ArgoCD self-manages.

**⚠️ Agent must verify before writing:**
- The exact **`ArgoCD` CR field** for resource customizations on the *installed operator version*. Field has drifted across versions: older `spec.resourceCustomizations` (string blob) vs `spec.extraConfig: resource.customizations:` vs structured `spec.resourceHealthChecks`. Use the form valid for the installed version; the documented-working example uses `spec.extraConfig`. **Confirm against the live operator.**
- **Compatibility caveat:** cluster is **OpenShift 4.22 (RC build)**; published GitOps-operator support matrix may not list 4.22 yet. `latest` will very likely install fine (forward-compatible) but if the Subscription stalls, this gap is the first suspect.

**Acceptance:** operator installed; the dedicated `argocd`-namespace ArgoCD instance is Running and reachable; the default instance is NOT created; root app syncs (even if it has nothing to deploy yet).

### Phase 2 — OpenShift platform infrastructure (`clusters/openshift/infrastructure/`)
Platform layer the workloads land on (the cluster "comes ready"):
- **Gateway API platform:** `GatewayClass` (controllerName `openshift.io/gateway-controller/v1`) + a `Gateway` in `openshift-ingress`, HTTPS listener on `*.apps.sno-ai-lab.vanillax.xyz`.
- **cert-manager** (via OLM) + replicate the existing **Cloudflare DNS-01** `ClusterIssuer`/`Certificate` pattern (Cloudflare API token from 1Password via ESO) to mint the wildcard cert for the Gateway listener. (DNS-01 because cluster has no public inbound.)
- **ESO + ClusterSecretStore `1password`** on the spoke (1Password Connect pre-seeded once, manually, per existing Step-3 pattern; then GitOps).
- **LVM Storage operator** + `LVMCluster` on the second NVMe (`nvme1n1`) → default StorageClass `lvms-vg1`.

**Acceptance:** Gateway shows `Programmed=True`; cert issued; `lvms-vg1` is the default SC; ESO `ClusterSecretStore` healthy.

### Phase 3 — First shared app: Redlib (`apps-shared/redlib/`)
- `base/`: Deployment (`quay.io/redlib/redlib:latest`, port 8080, **stateless**), Service, `HTTPRoute` (empty `parentRefs`, PathPrefix `/`). Bake OpenShift-friendly `securityContext` into base (runAsNonRoot, drop ALL caps, seccomp RuntimeDefault, **no hardcoded runAsUser/fsGroup** — let OCP SCC assign).
- `overlays/talos/`: patch `parentRefs` → `gateway-internal`/`gateway`/`https`, hostname `redlib.vanillax.me`, namespace `redlib`.
- `overlays/openshift/`: patch `parentRefs` → OpenShift Gateway, hostname `redlib.apps.sno-ai-lab.vanillax.xyz`, namespace `redlib`.
- Create the **OpenShift apps AppSet** (directory generator over `apps-shared/*/overlays/openshift`) in an isolated AppProject, with the Gateway-API `ignoreDifferences` carried over from existing AppSets. Optionally add an **additive** Talos AppSet over `apps-shared/*/overlays/talos` (do NOT modify the existing live `my-apps/*/*` generator in this phase).

**Why Redlib first:** stateless, no DB, no PVC, non-root — isolates the *ingress/Gateway portability* lesson with zero storage/SCC noise.

**Acceptance:** Redlib reachable at `redlib.vanillax.me` (Talos) and `redlib.apps.sno-ai-lab.vanillax.xyz` (OpenShift); the only diff between overlays is `parentRefs`+hostname.

### Phase 4 — Talos migration into `clusters/talos/`
Move existing root-level trees (`infrastructure/`, `my-apps/`, `monitoring/`, bootstrap) into `clusters/talos/`. Repoint `root.yaml` and all AppSet generator `path:` values to the new locations.

**⚠️ Critical acceptance gate:** the set of **rendered Applications must be identical** (same names, namespaces, destinations) before vs after the move, so ArgoCD *adopts* existing resources rather than recreating them → **zero workload churn**. Validate with `argocd appset generate` / dry diff on a branch before merge. The owner is fine with touching root; correctness (no churn) is the concern, not caution.

**Acceptance:** branch shows identical generated Applications; live cluster reconciles with no unexpected diffs/recreations after merge.

### Phase 5 — Second app (stateful) + backup pattern replication
Pick a utility/stateful app (single PVC, maybe CNPG). This is where the hard cross-platform lessons land: `storageClassName` overlay, **SCC friction** (the big one — many upstream images need securityContext adjustment on OpenShift), CNPG on the spoke, and **replicating the backup/restore pattern**.

**⚠️ Agent must read the live repo here:** the backup/restore design has **changed** — Kyverno was **removed** and replaced/reworked around **PVC Plumber**. The public docs index is stale and still shows the old Kyverno-coupled design. **Do NOT assume the old design.** Read the current `pvc-plumber` setup and however PVC backup-label→restore-injection now works (native admission policy? PVC Plumber doing it directly?), then port *that* to OpenShift. Ask the human to confirm the current design if the repo is ambiguous.

**Acceptance:** stateful app runs on both clusters; PVCs use correct SC per platform; SCC issues resolved via overlay; backups land on the same TrueNAS NFS target.

### Phase 6 — Specialize OpenShift (future / GPU + AI)
Lean into what makes the OpenShift box purposeful (it's `sno-ai-lab`):
- **GPU stack:** NFD operator → verify `feature.node.kubernetes.io/pci-10de.present`, then NVIDIA GPU Operator → `ClusterPolicy`. **Note:** current card is a GeForce **GTX 1050 Ti** (unsupported-but-works, Pascal); owner plans to install **RTX 3090(s)** (Ampere — well-supported in practice, far smoother). Build/validate the stack against the 3090s when installed. Multi-GPU: node reports `nvidia.com/gpu: "N"`; plan power/cooling/PCIe; optional NVLink.
- **OpenShift Virtualization** (already installed) for GPU-passthrough VMs (needs IOMMU enabled in BIOS — verify; also needed alongside SVM for CNV).
- **OpenShift AI** + Gateway API Inference Extensions (GIE) for model serving — Gateway API here is also the inference-routing substrate.

Decide per use: GPU for **containers** (pods/OpenShift AI — standard NFD→Operator→ClusterPolicy) vs **VM passthrough** (extra HyperConverged/IOMMU config). Ask the human which.

**Acceptance:** (when 3090s in) node reports `nvidia.com/gpu`; a test CUDA workload (or VM) consumes a GPU.

---

## 5. Open Questions for the Agent to Resolve Against the Live Repo
Resolve these by **reading the repo and/or asking the human** — do not assume:
1. Exact **ArgoCD CR schema field** for health checks on the installed GitOps-operator version (see Phase 1 warning).
2. **Current post-Kyverno PVC Plumber / backup-restore design** (see Phase 5 warning). The planning convo only had the stale Kyverno-coupled version.
3. Exact **AppSet generator syntax/version** in use (directory generator path templating; how namespace is derived — existing convention is namespace = app dir basename via `{{path.basename}}`; deeper overlay paths may need a different path segment).
4. Whether to do the **Talos migration (Phase 4) now or after** the OpenShift side is fully proven (lower risk to defer; owner is fine either way).
5. Exact **Cilium Gateway** name/namespace/listener for the Talos overlay `parentRefs` (planning assumed `gateway-internal`/`gateway`/`https` — verify in repo).
6. Redlib's **current manifests** if it already exists in `my-apps/privacy/redlib` — refactor *those* (preserve env/limits/labels) rather than generic.

## 6. Flagged Risks / Things Not Verified
- **OpenShift 4.22-RC vs GitOps-operator compatibility** may lag the support matrix (Phase 1).
- **AppSet-discovery refactor** can ripple into the ~200 live Talos apps — isolate via additive AppSets (Phase 3) and the identical-render gate (Phase 4).
- **SCC friction** will be the main per-app surprise on OpenShift (Phase 5).
- **GeForce vs datacenter GPU**: 1050 Ti / 3090 are unsupported-on-paper by the GPU Operator; 3090 works well in practice, 1050 Ti may need driver pinning (Phase 6).
- **Stale public repo index**: the agent must trust the *live working tree*, not external docs/wikis, wherever they conflict (this whole PRD was drafted partly blind).

## 7. Working Style for the Agent
- Read the live repo first each phase; reconcile with this PRD; surface conflicts.
- **Ask focused questions** at decision points and before any destructive/structural change. Re-prompting the human is the intended workflow.
- Work in small, reviewable commits on a branch; validate (`kustomize build`, `argocd appset generate`, dry diffs) before applying.
- Preserve existing conventions (sync waves, `ignoreDifferences`, selfHeal exceptions, ESO patterns) unless explicitly changing them.
- Keep install-method divergence quarantined in `bootstrap/`; keep everything else portable.