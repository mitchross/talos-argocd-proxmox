# Official TrueNAS CSI Migration Design

## Goal

Replace the undeployed Democratic CSI configuration with the official
`truenas/truenas-csi` driver for dynamically provisioned NFS storage while
leaving Longhorn and the existing Kubernetes NFS CSI deployment unchanged.

## Current State

- `infrastructure/storage/democratic-csi/` defines Democratic CSI NFS and
  iSCSI releases, but the live Argo CD ApplicationSet has not reconciled that
  path.
- The live cluster has no `org.democratic-csi.*` drivers, no
  `truenas-nfs`/`truenas-iscsi` StorageClasses, and no PVs provisioned by
  either Democratic CSI or TrueNAS CSI.
- TrueNAS runs SCALE 26 beta, satisfying the official driver's SCALE
  `25.10.0+` requirement.
- Kubernetes `1.36.1`, Talos `1.13.2`, and the existing snapshot controller
  satisfy the remaining platform prerequisites.

No persistent-volume data migration is required if the replacement lands
before Democratic CSI is deployed.

## Architecture

Deploy one official TrueNAS CSI controller and one node DaemonSet in the
`truenas-csi` namespace. The driver registers `csi.truenas.io`; protocol
selection remains a StorageClass parameter.

The first rollout exposes only an NFS StorageClass:

- StorageClass: `truenas-nfs`
- Pool: `BigTank`
- Dataset parent: `BigTank/k8s/nfs/v`
- Reclaim policy: `Retain`
- Binding: `Immediate`
- NFS: version 4.1 with the cluster's existing 10 Gb tuning

The following storage systems remain separate:

- `longhorn`: default RWO application storage and VolSync source snapshots.
- `nfs.csi.k8s.io`: static or pre-existing NFS shares used by media and AI
  workloads.
- `smb.csi.k8s.io`: existing SMB shares.

No `truenas-iscsi` StorageClass is created in this rollout. The official node
plugin still retains its upstream iSCSI-capable shape, but iSCSI provisioning
requires a separate canary and approval.

## GitOps Packaging

The upstream project does not publish a Helm chart. Vendor its Kubernetes
resources into `infrastructure/storage/truenas-csi/` and pin the driver to
`v1.0.4` plus its published multi-architecture image digest.

Repository-owned configuration is split from the upstream-derived workload:

- `namespace.yaml`: namespace and privileged Pod Security labels.
- `rbac.yaml`: service accounts, cluster roles, and bindings.
- `driver.yaml`: `CSIDriver`, controller Deployment, and node DaemonSet.
- `configmap.yaml`: TrueNAS WebSocket endpoint and storage defaults.
- `externalsecret.yaml`: API key material from 1Password.
- `storageclass.yaml`: NFS provisioning policy.
- `volumesnapshotclass.yaml`: CSI snapshot integration.
- `canary/`: manually applied, disposable validation resources.

The Argo CD infrastructure ApplicationSet atomically changes from the
Democratic CSI path to the TrueNAS CSI path.

## Security And Networking

Use a dedicated TrueNAS service account and API key. On TrueNAS 26,
`SHARING_ADMIN` covers dataset and sharing operations. Snapshot and periodic
snapshot-task operations require the associated snapshot roles if those
features are enabled.

TrueNAS roles are API-method scoped, not dataset-path scoped. The CSI
credential therefore has broad storage authority even when StorageClasses
place new datasets under `BigTank/k8s/nfs/v`. Keep the key isolated in
1Password and expose it only through an `ExternalSecret`.

The cluster-wide Cilium LAN policy must allow TCP `443` from pods to
`192.168.10.133` for `wss://192.168.10.133/api/current`. Existing NFS port
allowances remain unchanged. TCP `3260` is not opened until iSCSI is enabled.

## NFS Identity Caveat

Official TrueNAS CSI `v1.0.4` creates NFS shares using `mapall`, defaulting to
`root:wheel`. Democratic CSI was configured with `maproot`, which preserves
non-root client identities.

This is not behaviorally equivalent. A canary must verify:

- writes as root;
- writes as UID/GID `1000`;
- ownership observed from a second pod and node;
- compatibility with pod `fsGroup` behavior.

No production workload should adopt `truenas-nfs` until its required ownership
semantics are explicitly accepted.

## Validation And Rollback

Repository validation checks that:

- Democratic CSI is absent from the rendered topology;
- `csi.truenas.io` is registered exactly once;
- the driver image is version and digest pinned;
- the secret is supplied by External Secrets;
- Longhorn remains the default StorageClass;
- TrueNAS TCP `443` egress is allowed;
- no iSCSI StorageClass is introduced.

The live canary covers provisioning, two-node RWX access, persistence,
ownership, expansion, snapshot creation, clone restore, and retained-volume
cleanup.

Rollback before production adoption is removal of the TrueNAS CSI Application
and restoration of the previous Git path. Once a PV uses `csi.truenas.io`,
the driver must remain installed until that PV is migrated or deleted.

