# PRD: Cluster-Centric Multicluster Kustomize GitOps

## Plain-English Summary

This repository supports one complete Talos reference cluster and independent
expansion clusters such as OpenShift or future GKE clusters.

Each cluster runs its own upstream Helm Argo CD. That Argo CD reads only its
own `clusters/<cluster>` directory and deploys only to the local cluster.

Shared workload definitions live under `manifests/`. Cluster-specific
Kustomize overlays live directly under `clusters/<cluster>/`. Talos and
OpenShift both use Gateway API, but each platform owns its GatewayClass,
Gateway, domain, storage implementation, security behavior, and bootstrap
prerequisites.

The approved model is:

```text
shared Talos-first base + explicit per-cluster overlay + local Argo CD
```

The detailed design is:

```text
docs/superpowers/specs/2026-06-04-multicluster-kustomize-and-bootstrap-design.md
```

## Goals

- Keep Talos the complete default reference cluster.
- Make additional clusters independently bootstrappable and optional.
- Run one local upstream Helm Argo CD per cluster.
- Make `clusters/<cluster>` the only deployable source tree for that cluster.
- Reuse shared workload definitions without making one cluster inherit from
  another.
- Keep cluster differences readable and explicit.
- Preserve current Argo CD sync waves and application boundaries.
- Use Gateway API on Talos and OpenShift.
- Make adding a future cluster a repeatable profile-and-overlay operation.

## Non-Goals

- No hub-and-spoke Argo CD.
- No remote cluster registration or `argocd cluster add`.
- No Matrix or cluster generators.
- No OpenShift GitOps Operator.
- No Cilium or Longhorn installation on OpenShift.
- No broad neutral-base or component-driven rewrite.
- No automatic cross-cluster failover.
- No claim that every stateful app is production-ready on OpenShift.

## Repository Shape

```text
clusters/
  talos/
    bootstrap/                    # hand-run seed and root Application
    argocd/                       # self-managed projects, AppSets, entrypoints
    apps/<category>/<app>/        # Talos app overlays
    infra/<component>/            # Talos infrastructure
    database/<engine>/<name>/     # Talos databases
    monitoring/<component>/       # Talos monitoring

  openshift/
    bootstrap/                    # hand-run seed and root Application
    argocd/                       # self-managed projects, AppSets, entrypoints
    apps/<category>/<app>/        # OpenShift app overlays
    infra/<component>/            # OpenShift infrastructure

manifests/
  apps/<category>/<app>/base/     # shared app definitions
  infra/<component>/base/         # shared infrastructure where practical
  database/...
  monitoring/...
```

No additional `clusters/<cluster>/overlays` directory is required. Everything
below `clusters/<cluster>` is already cluster-owned overlay or entrypoint
content.

## Kustomize Contract

Shared bases are reusable, but currently Talos-first. Some shared app bases
contain Talos backup and restore policy that OpenShift overlays explicitly
remove. Fully neutralizing those bases is future work.

Each cluster overlay consumes a shared base and owns its routes, storage
changes, security compatibility, and other platform differences.

Rules:

- Cluster overlays may reference `manifests/**`.
- Cluster overlays must never reference another cluster's tree.
- Use `resources:` instead of deprecated `bases:`.
- Use unified `patches:` instead of deprecated `patchesStrategicMerge:` or
  `patchesJson6902:`.
- Prefer external declarative YAML patches for ordinary changes.
- Reserve external JSON6902 patches for precise removals and list-sensitive
  changes.
- Do not use escaped patch strings.
- Externalize remaining multiline inline patches.
- Keep HTTPRoutes as complete cluster-owned resources.
- Add Kustomize components only when a repeated optional feature proves the
  abstraction useful.

## Argo CD Contract

Each cluster root Application remains outside its self-managed Argo CD tree:

```text
clusters/talos/bootstrap/root.yaml
  -> clusters/talos/argocd

clusters/openshift/bootstrap/root.yaml
  -> clusters/openshift/argocd
```

All sources use `targetRevision: main`. All destinations use:

```yaml
server: https://kubernetes.default.svc
```

App overlays are uniform and should be discovered by Git directory generators:

```text
clusters/talos/apps/*/*
clusters/openshift/apps/*/*
```

App metadata is derived from directory paths. App `.argocd/config.json` files
are removed because they contain no current exceptions.

The app ApplicationSets use fixed projects:

- `talos-apps`
- `openshift-apps`

Infrastructure, database, monitoring, bootstrap dependencies, and standalone
entrypoints retain explicit discovery and Applications where allowlists,
ordering, or namespace exceptions matter.

## Gateway API Contract

Gateway API is the common routing API on both platforms.

Talos:

- Cilium provides Gateway API.
- Talos bootstrap installs or verifies pinned Cilium.
- Talos bootstrap installs upstream Gateway API CRDs.
- Talos owns `*.vanillax.me` routes.

OpenShift/OKD 4.20:

- The Ingress Operator owns Gateway API CRDs and implementation lifecycle.
- OpenShift bootstrap must not install upstream Gateway API CRDs.
- The OpenShift Gateway infrastructure entrypoint declares GatewayClass
  `openshift-default` with controller `openshift.io/gateway-controller/v1`.
- The shared Gateway lives in `openshift-ingress`.
- OpenShift owns `*.apps.sno-ai-lab.vanillax.xyz` routes.
- The OpenShift bootstrap profile verifies there is no active OSSM v2
  subscription that conflicts with the Ingress Operator-managed OSSM v3
  Gateway implementation.
- The Gateway infrastructure Application applies the GatewayClass before the
  Gateway. Application HTTPRoutes remain later-wave resources.
- cert-manager Gateway API support remains enabled.

## Storage and Backup Contract

Portable local ReadWriteOnce PVCs use:

```text
vanillax-local-rwo
```

Implementations:

- Talos: Longhorn `driver.longhorn.io`.
- OpenShift: LVM Storage `topolvm.io`, device class `vg1`.

NFS, SMB, and static storage remain explicit where they identify real external
shares or datasets.

Talos pvc-plumber, VolSync, restore labels, and restore `dataSourceRef` fields
remain Talos policy. OpenShift overlays currently remove that policy and do not
claim equivalent app PVC backup coverage.

## Bootstrap Contract

Bootstrap is driven by a cluster profile because platform choice controls more
than Cilium:

```bash
./scripts/bootstrap-cluster.sh talos
./scripts/bootstrap-cluster.sh openshift
./scripts/bootstrap-cluster.sh gke
```

`bootstrap-cluster.sh` is the one-shot operator entrypoint. It performs
profile-specific prerequisites and then calls
`scripts/bootstrap-argocd.sh <cluster>` for the focused upstream Argo CD and
local-root bootstrap.

The profile selects the cluster bootstrap directory, prerequisites, networking
behavior, Gateway API behavior, Argo CD Helm values, root Application, and
validation.

Expected defaults:

| Behavior | Talos | OpenShift |
|---|---|---|
| Install or verify Cilium | Yes | No |
| Install upstream Gateway API CRDs | Yes | No |
| GatewayClass ownership | Cilium-owned | GitOps `openshift-default` |
| Check OSSM v2 conflict | No | Yes |
| Install upstream Helm Argo CD | Talos values | OpenShift values |
| Apply root | Talos root | OpenShift root |

An optional `--cilium=auto|install|skip` override supports recovery cases. The
default `auto` behavior installs or verifies Cilium on Talos and skips Cilium
on OpenShift. Installing Cilium is invalid for the OpenShift profile.

## One-Shot Migration Requirement

The implementation migrates the complete app catalog and supporting structure
in one branch. It is not a pilot or partial app rollout.

The implementation must:

1. Preserve all generated Application names and destinations.
2. Switch app discovery to directory generators.
3. Remove app `.argocd/config.json` boilerplate.
4. Externalize remaining inline patches without changing rendered behavior.
5. Add profile-driven bootstrap behavior and OpenShift GatewayClass ownership.
6. Update README, runbooks, validation, planning docs, and Mink decisions.

## Schema Assumptions To Verify Live

Local rendering cannot prove:

- OpenShift 4.20 GatewayClass and controller behavior.
- Absence of a conflicting OSSM v2 subscription.
- LVM Storage Operator Subscription channel and `LVMCluster` schema.
- The generated LVM device class and TopoLVM StorageClass behavior.
- OpenShift SCC compatibility for NFS, SMB, applications, and Helm charts.
- External storage network reachability.
- cert-manager Gateway shim behavior on the intended OpenShift cluster.

## Validation

No validation command below mutates a live cluster:

```bash
./scripts/validate-cluster-layout.sh
./scripts/validate-argocd-apps.sh

kustomize build --enable-helm clusters/talos/bootstrap
kustomize build --enable-helm clusters/openshift/bootstrap
kustomize build clusters/talos/argocd
kustomize build clusters/openshift/argocd

find clusters -type f -name kustomization.yaml -print \
  | while read -r file; do
      kustomize build --enable-helm "$(dirname "$file")" >/dev/null
    done
```

Implementation validation must additionally prove:

- exactly 44 Talos and 44 OpenShift app overlays are discovered;
- generated Application names remain unchanged;
- all app destinations remain local;
- all app projects remain fixed;
- app `.argocd/config.json` files are gone;
- no new escaped or multiline inline patch strings remain.

Live verification requires an explicit operator decision before any
`kubectl apply`, `oc apply`, or Helm mutation.
