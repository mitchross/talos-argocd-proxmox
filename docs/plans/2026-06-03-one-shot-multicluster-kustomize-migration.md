# One-Shot Cluster-Centric Multicluster Migration

> **Status:** Historical structural migration record. The authoritative design
> for the remaining AppSet, Kustomize readability, Gateway API, and bootstrap
> work is
> `docs/superpowers/specs/2026-06-04-multicluster-kustomize-and-bootstrap-design.md`.

## Plain-English Summary

The repository has two cluster folders. Talos deploys from `clusters/talos`.
OpenShift deploys from `clusters/openshift`. Each cluster runs its own local
upstream Helm Argo CD and never manages the other cluster.

Shared app resources live under `manifests/apps/**/base`. Both cluster overlays
reference the same base when resources are common. Routes, storage
implementations, security compatibility patches, and backup behavior stay in
the cluster folder where they apply.

## Target Tree

```text
clusters/
  talos/
    bootstrap/
    argocd/
    apps/
    infra/
    database/
    monitoring/
  openshift/
    bootstrap/
    argocd/
    apps/
    infra/

manifests/
  apps/<category>/<app>/base/
  infra/<component>/base/
```

## Completed Structural Work

- Moved every deployable Argo entrypoint under its owning cluster.
- Moved all 44 app sources into shared bases.
- Created 44 Talos and 44 OpenShift app overlays.
- Made routes complete cluster-owned resources.
- Removed OpenShift inheritance from Talos.
- Replaced app `longhorn` references with `vanillax-local-rwo`.
- Implemented `vanillax-local-rwo` through Longhorn on Talos and LVM Storage on
  OpenShift.
- Added shared NFS and SMB CSI bases with overlays for both clusters.
- Externalized OpenShift security patches into readable files.
- Removed Talos pvc-plumber, VolSync, restore labels, and restore
  `dataSourceRef` fields from OpenShift renders.
- Updated AppSet discovery to scan `clusters/<cluster>`.
- Added `scripts/validate-cluster-layout.sh`.

## Remaining Live Verification

Local renders cannot prove the following:

- OpenShift GatewayClass name and controller behavior.
- LVM Operator API, channel, provisioner, and device class on the live cluster.
- NFS and SMB CSI SCC behavior.
- Application and Helm chart SCC behavior.
- External storage network reachability.
- OpenShift application callback and base URLs.
- OpenShift backup and restore policy.

## Validation

```bash
./scripts/validate-cluster-layout.sh
./scripts/validate-argocd-apps.sh

find clusters -type f -name kustomization.yaml -print \
  | while read -r file; do
      kustomize build --enable-helm "$(dirname "$file")" >/dev/null
    done
```

No live cluster mutation is part of this migration validation.
