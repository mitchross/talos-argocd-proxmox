# PRD: Cluster-Centric Multicluster Kustomize GitOps

## Plain-English Summary

This repository has two independent cluster folders: `clusters/talos` and
`clusters/openshift`.

Each cluster has its own bootstrap inputs, local upstream Helm Argo CD, Argo CD
entrypoint tree, infrastructure, databases or monitoring where applicable, and
application overlays. Each cluster's Argo CD reads only its own cluster folder
and manages only `https://kubernetes.default.svc`.

Shared workload definitions live under `manifests/**/base`. A cluster overlay
references a shared base when the workload is the same. When a resource is
platform-specific, such as an HTTPRoute, storage implementation, SCC adjustment,
or Talos backup policy, that resource lives in the owning cluster folder.

The result is normal Kustomize:

```text
shared base + Talos overlay
shared base + OpenShift overlay
```

There is no OpenShift-to-Talos inheritance, no hub/spoke Argo CD, and no escaped
inline patch strings.

## Goals

- Keep Talos the default full homelab reference cluster.
- Keep OpenShift additive and independently bootstrappable.
- Run one local upstream Helm Argo CD per cluster.
- Make `clusters/<cluster>` the only deployable Argo CD source tree.
- Put genuinely shared app and infrastructure resources in `manifests/**/base`.
- Keep cluster differences readable and explicit.
- Preserve current Argo CD sync waves and application boundaries.
- Make adding a future cluster a repeatable folder-and-overlay operation.

## Non-Goals

- No hub/spoke Argo CD.
- No remote cluster registration or `argocd cluster add`.
- No OpenShift GitOps Operator.
- No OpenShift Cilium or Longhorn installation.
- No automatic cross-cluster failover.
- No claim that every stateful app is production-ready on OpenShift.

## Repository Shape

```text
clusters/
  talos/
    bootstrap/                    # hand-run Argo CD seed
    argocd/                       # root app, projects, AppSets, sync waves
    apps/<category>/<app>/        # Talos app overlays and routes
    infra/<component>/            # Talos infrastructure entrypoints
    database/<engine>/<name>/     # Talos database entrypoints
    monitoring/<component>/       # Talos monitoring entrypoints

  openshift/
    bootstrap/                    # hand-run Argo CD seed
    argocd/                       # root app, projects, AppSets, sync waves
    apps/<category>/<app>/        # OpenShift app overlays and routes
    infra/<component>/            # OpenShift infrastructure entrypoints

manifests/
  apps/<category>/<app>/base/     # shared app resources
  infra/<component>/base/         # shared infra only when truly portable
```

## Kustomize Contract

An application base contains shared Deployments, Services, PVCs, config, and
other portable resources:

```yaml
# manifests/apps/media/echo-server/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespace.yaml
  - deployment.yaml
  - service.yaml
```

Each cluster overlay consumes that base and owns its route or platform patches:

```yaml
# clusters/openshift/apps/media/echo-server/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: echo-server
resources:
  - ../../../../../manifests/apps/media/echo-server/base
  - httproute.yaml
patches:
  - path: patches/deployment-echo-server.jsonpatch.yaml
    target:
      group: apps
      version: v1
      kind: Deployment
      name: echo-server
```

Rules:

- A cluster overlay may reference `manifests/**/base`.
- An OpenShift overlay must never reference `clusters/talos`.
- HTTPRoutes are complete cluster-owned resources, not hostname replacement
  patches.
- JSON patches are external readable files and are reserved for precise field
  removal where merge patches are unsafe.
- Talos backup labels and restore `dataSourceRef` fields are stripped by
  OpenShift overlays.
- The migration preserves each app's current activation state. Intentionally
  disabled resources such as DVWA and Project Nomad's Kolibri remain disabled.

## Argo CD Contract

AppSets discover metadata only inside their cluster:

```text
clusters/talos/apps/*/*/.argocd/config.json
clusters/openshift/apps/*/*/.argocd/config.json
clusters/talos/database/*/*/.argocd/config.json
clusters/talos/monitoring/*/.argocd/config.json
clusters/<cluster>/infra/*/.argocd/config.json
```

Each metadata file declares an explicit `sourcePath` under its owning cluster.
All Argo CD sources use `targetRevision: main`.

OpenShift AppProjects are:

- `openshift-infrastructure`
- `openshift-apps`

## Storage Contract

Portable local ReadWriteOnce PVCs use:

```text
vanillax-local-rwo
```

Implementations:

- Talos: Longhorn `driver.longhorn.io`.
- OpenShift: LVM Storage `topolvm.io`, device class `vg1`.

NFS and SMB are shared infrastructure bases consumed by both clusters. Existing
NFS, SMB, and static-PV class names remain explicit because they identify real
external shares or datasets.

Talos pvc-plumber, VolSync, restore labels, and restore `dataSourceRef` fields
remain Talos-only policy. OpenShift app overlays remove them and currently do
not claim equivalent app PVC backup coverage.

This storage-class migration assumes the planned fresh Talos rebuild because a
bound PVC's `storageClassName` is immutable.

## Cluster Differences

Talos owns:

- Cilium and Cilium Gateway API.
- `*.vanillax.me` routes.
- Longhorn and the `vanillax-local-rwo` Longhorn StorageClass.
- VolSync, pvc-plumber, snapshot controller, and backup policy.
- CNPG databases, monitoring, GPU infrastructure, and the full app catalog.

OpenShift owns:

- OpenShift Gateway API resources.
- `*.apps.sno-ai-lab.vanillax.xyz` routes.
- LVM Storage and the `vanillax-local-rwo` TopoLVM StorageClass.
- SCC-compatible security removals where currently required.
- Shared NFS and SMB CSI drivers.
- The full app catalog for compatibility testing.

The full catalog means every app has a cluster overlay. It does not implicitly
enable resources that were intentionally disabled before the migration.

## Bootstrap Contract

Both clusters use the same operator flow:

1. Obtain cluster access.
2. Satisfy cluster-specific prerequisites.
3. Pre-seed 1Password secrets.
4. Run `./scripts/bootstrap-argocd.sh <cluster>`.
5. Apply the cluster root Application.
6. Let that cluster's local Argo CD reconcile only its cluster tree.

Commands:

```bash
./scripts/bootstrap-argocd.sh talos
./scripts/bootstrap-argocd.sh openshift
```

## Schema Assumptions To Verify Live

These render locally but require verification against the intended OpenShift
cluster before live sync:

- GatewayClass name is `openshift-default`.
- LVM Storage Operator Subscription channel is `stable-4.20`.
- `LVMCluster` uses `lvm.topolvm.io/v1alpha1`.
- The generated LVM device class is `vg1`.
- The portable StorageClass provisioner is `topolvm.io` with parameter
  `topolvm.io/device-class: vg1`.
- OpenShift permits the upstream NFS and SMB CSI chart resources.
- cert-manager Gateway shim behavior works with the OpenShift Gateway.
- Remaining application images and Helm charts satisfy OpenShift SCC behavior.

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

Live verification must begin with a context check and requires an explicit
operator decision before any `kubectl apply`, `oc apply`, or Helm mutation.
