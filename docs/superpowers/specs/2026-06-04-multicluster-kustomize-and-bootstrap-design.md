# Multicluster Kustomize and Bootstrap Design

**Status:** Approved design  
**Date:** 2026-06-04  
**Platforms:** Talos, OpenShift/OKD, future Kubernetes targets  
**Orchestration:** One local upstream Helm Argo CD per cluster

## Plain-English Summary

This repository uses one shared Git source but does not use one shared Argo CD.
Every cluster runs its own Argo CD, watches only its own cluster directory, and
deploys only to `https://kubernetes.default.svc`.

Shared workload definitions live under `manifests/`. Deployable cluster
overlays live directly under `clusters/<cluster>/`. The cluster directory is
already the overlay boundary, so an additional `overlays/` directory would add
depth without adding meaning.

The target model is:

```text
shared Talos-first base + Talos overlay
shared Talos-first base + OpenShift overlay
```

Talos remains the complete reference implementation. OpenShift is an
independent expansion target with its own routing, storage, security
compatibility, and bootstrap behavior. A future GKE target follows the same
contract without requiring a centralized Argo CD.

## Decisions

- Keep the current cluster-centric directory structure.
- Run one independent local Argo CD in each cluster.
- Keep every generated Application destination local.
- Use `targetRevision: main` everywhere.
- Use Gateway API on both Talos and OpenShift.
- Use cluster profile defaults for bootstrap behavior.
- Use Git directory generators for the uniform app overlay trees.
- Keep explicit infrastructure, database, monitoring, and standalone Argo CD
  entrypoints where ordering, namespaces, or allowlists matter.
- Keep `kustomization.yaml` files readable as tables of contents.
- Prefer external declarative YAML patches for ordinary field changes.
- Reserve external JSON6902 patches for precise removals and list-sensitive
  operations.
- Do not introduce Kustomize components until repeated optional behavior
  demonstrates a concrete need.
- Do not claim the current shared bases are neutral. They are reusable
  Talos-first bases, and some OpenShift overlays remove Talos backup policy.

## Target Repository Structure

```text
clusters/
  talos/
    bootstrap/                    # hand-run seed inputs and root Application
    argocd/                       # self-managed projects, AppSets, entrypoints
    apps/<category>/<app>/        # Talos app overlays
    infra/<component>/            # Talos infrastructure entrypoints
    database/<engine>/<name>/     # Talos database entrypoints
    monitoring/<component>/       # Talos monitoring entrypoints

  openshift/
    bootstrap/                    # hand-run seed inputs and root Application
    argocd/                       # self-managed projects, AppSets, entrypoints
    apps/<category>/<app>/        # OpenShift app overlays
    infra/<component>/            # OpenShift infrastructure entrypoints

manifests/
  apps/<category>/<app>/base/     # shared, reusable app definitions
  infra/<component>/base/         # shared infrastructure where practical
  database/...                    # shared database definitions where practical
  monitoring/...                  # shared monitoring definitions where practical
```

`clusters/<cluster>/apps` is equivalent to a conventional
`clusters/<cluster>/overlays/apps` tree. Adding the extra `overlays` directory
would not improve isolation or discovery.

## Argo CD Architecture

Each cluster is bootstrapped with upstream Helm Argo CD and its own root
Application:

```text
clusters/talos/bootstrap/root.yaml
  -> clusters/talos/argocd

clusters/openshift/bootstrap/root.yaml
  -> clusters/openshift/argocd
```

The root Application stays outside the directory it manages. This keeps the
hand-run seed separate from the self-managed Argo CD tree.

Every generated or standalone Application must use:

```yaml
destination:
  server: https://kubernetes.default.svc
```

There is no remote cluster registration, cluster generator, Matrix generator,
or hub-and-spoke control plane.

### App Discovery

The app trees are uniform:

```text
clusters/talos/apps/<category>/<app>/kustomization.yaml
clusters/openshift/apps/<category>/<app>/kustomization.yaml
```

App ApplicationSets should use Git directory generators:

```yaml
generators:
  - git:
      repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
      revision: main
      directories:
        - path: clusters/talos/apps/*/*
```

The owning ApplicationSet fixes the cluster-wide values:

```yaml
project: talos-apps
destination:
  server: https://kubernetes.default.svc
  namespace: "{{.path.basename}}"
```

Application names, source paths, category names, and namespaces are derived
from the directory path. App `.argocd/config.json` files are removed because
their current values are fully derivable and contain no exceptions.

The equivalent OpenShift ApplicationSet fixes `project: openshift-apps` and
discovers only `clusters/openshift/apps/*/*`.

### Explicit Discovery

Infrastructure, database, monitoring, bootstrap dependencies, and custom
entrypoints do not automatically switch to directory discovery.

Talos has explicit allowlists and standalone Applications created to preserve
dependency order, avoid double management, and handle namespace exceptions.
Those entrypoints remain explicit until reviewed independently.

## Kustomize Contract

A shared app base defines the reusable workload:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespace.yaml
  - deployment.yaml
  - service.yaml
  - pvc.yaml
```

A cluster overlay consumes the base and owns cluster-specific resources:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: home-assistant
resources:
  - ../../../../../manifests/apps/home/home-assistant/base
  - httproute.yaml
patches:
  - path: patches/deployment-openshift.jsonpatch.yaml
  - path: patches/remove-talos-backup-namespace.yaml
```

Rules:

- Use `resources:`, not the deprecated `bases:` field.
- Use the unified `patches:` field, not deprecated `patchesStrategicMerge:` or
  `patchesJson6902:` fields.
- Keep ordinary patches in external declarative YAML files.
- Keep JSON6902 patches external and limited to operations that require exact
  paths, especially OpenShift security-context and Talos-policy removals.
- Do not use escaped patch strings.
- Externalize remaining multiline inline patch blocks.
- Keep complete HTTPRoute resources in the owning cluster overlay.
- Do not make broad all-PVC transformations unless every selected PVC has the
  same storage intent.
- An OpenShift overlay must never reference `clusters/talos`.
- A Talos overlay must never reference `clusters/openshift`.

### Components

Kustomize components are appropriate for repeated optional features that need
to be composed into several overlays. They are not required for the current
readability cleanup.

Before adding a component, it must:

1. Represent one coherent optional behavior.
2. Be used by multiple overlays.
3. Remove meaningful duplication.
4. Preserve clear rendered ownership and build behavior.

## Gateway API Contract

Gateway API is the common routing API. The controllers and platform resources
are cluster-specific.

### Talos

- Cilium provides the Gateway API implementation.
- Bootstrap installs or verifies the pinned Cilium version.
- Bootstrap installs the required upstream Gateway API CRDs.
- Talos owns its Gateway and `*.vanillax.me` HTTPRoutes.

### OpenShift/OKD 4.20

- The OpenShift/OKD Ingress Operator manages Gateway API CRDs and the platform
  implementation.
- Bootstrap must not install upstream Gateway API CRDs.
- The OpenShift infrastructure Gateway entrypoint declares this GatewayClass:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: openshift-default
spec:
  controllerName: openshift.io/gateway-controller/v1
```

- The shared OpenShift Gateway lives in `openshift-ingress`.
- OpenShift owns `*.apps.sno-ai-lab.vanillax.xyz` HTTPRoutes.
- The OpenShift bootstrap profile verifies that no active OSSM v2 subscription
  conflicts with the Ingress Operator-managed OSSM v3 Gateway implementation.
- The Gateway infrastructure Application applies the GatewayClass before the
  Gateway. Application HTTPRoutes remain later-wave resources.
- cert-manager Gateway API support remains enabled for Gateway TLS issuance.

## Bootstrap Contract

Bootstrap is profile-driven because platform choice controls more than whether
Cilium is installed.

Target operator interface:

```bash
./scripts/bootstrap-cluster.sh talos
./scripts/bootstrap-cluster.sh openshift
./scripts/bootstrap-cluster.sh gke
```

`bootstrap-cluster.sh` is the one-shot operator entrypoint. It performs
profile-specific prerequisites and then calls the focused
`scripts/bootstrap-argocd.sh <cluster>` step to install upstream Argo CD and
apply the local root Application.

The profile selects:

- cluster bootstrap directory;
- prerequisite checks and installation actions;
- networking and Gateway API behavior;
- upstream Argo CD Helm values;
- local root Application;
- platform-specific validation.

Expected profile behavior:

| Behavior | Talos | OpenShift |
|---|---|---|
| Install or verify Cilium | Yes | No |
| Install upstream Gateway API CRDs | Yes | No |
| GatewayClass ownership | Cilium-owned | GitOps `openshift-default` |
| Check for OSSM v2 conflict | No | Yes |
| Install upstream Helm Argo CD | Talos values | OpenShift values |
| Apply local root | Talos root | OpenShift root |

An optional `--cilium=auto|install|skip` override supports recovery and
advanced use. The default is `auto`: Talos installs Cilium when absent and
verifies it when present; OpenShift skips it. `--cilium=install` is invalid for
the OpenShift profile.

The current `scripts/bootstrap-argocd.sh <cluster>` remains the focused Argo CD
bootstrap step. The new wrapper preserves the cluster-owned bootstrap inputs
and provides the complete one-shot workflow.

## Storage and Backup Contract

Portable local ReadWriteOnce PVCs use the storage contract
`vanillax-local-rwo`:

- Talos implements it with Longhorn.
- OpenShift implements it with LVM Storage and TopoLVM.

NFS, SMB, and static storage remain explicit where they identify real external
shares or datasets.

Talos pvc-plumber, VolSync, restore labels, and restore `dataSourceRef` fields
remain Talos policy. Current shared app bases still contain some of that
policy, so OpenShift overlays remove it. Moving all Talos policy out of shared
bases is a separate higher-risk refactor and is not required for this design.

## One-Shot Migration Scope

The approved implementation is one coherent branch migration, not a staged
partial app rollout. All app overlays move to the approved discovery and
readability contract together.

The work is still executed in a safe order:

1. Add validation that snapshots existing generated Application names and
   rendered outputs.
2. Change app ApplicationSets to directory generators while preserving names,
   projects, paths, namespaces, sync waves, and destinations.
3. Remove app `.argocd/config.json` files.
4. Externalize remaining inline patches without changing rendered output.
5. Add the profile-driven bootstrap behavior and OpenShift GatewayClass
   ownership.
6. Update README, runbooks, PRD, and Mink notes to match the resulting system.

## Safety and Validation

Changing an ApplicationSet generator can cause generated Applications to be
deleted if names or generator results change. Before rollout, compare the
current and proposed generated Application sets exactly.

No design or local validation step mutates a live cluster.

Required local checks include:

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

Additional implementation validation must prove:

- exactly 44 Talos and 44 OpenShift app overlays are discovered;
- generated Application names remain unchanged;
- every generated Application stays in its fixed cluster AppProject;
- every generated destination remains `https://kubernetes.default.svc`;
- Talos app renders remain behaviorally unchanged;
- OpenShift app renders contain no unintended Talos backup policy;
- no app `.argocd/config.json` files remain;
- no new escaped or multiline inline patch strings remain;
- OpenShift GatewayClass schema and controller behavior are verified before
  live sync;
- the intended OpenShift cluster has no conflicting OSSM v2 subscription.

## Out of Scope

- Centralized or hub-and-spoke Argo CD.
- OpenShift GitOps Operator.
- Matrix or cluster generators.
- Installing Cilium on OpenShift.
- Reorganizing the cluster trees beneath an additional `overlays/` directory.
- A broad neutral-base or component-driven rewrite.
- Automatic cross-cluster failover.
- Claiming every stateful app is production-ready on OpenShift.
