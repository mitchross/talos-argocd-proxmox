# OpenShift Storage And App Migration Strategy

## Plain-English Summary

OpenShift receives the same app catalog through its own overlays, but it does
not inherit Talos infrastructure or backup behavior.

Small local PVCs use the portable `vanillax-local-rwo` contract. Talos backs
that contract with Longhorn; OpenShift backs it with LVM Storage. Large or
shared datasets continue to use explicit NFS, SMB, or static PV definitions.

## Implemented Storage Paths

### Portable Local RWO

Use `vanillax-local-rwo` for ordinary application state:

- Talos provisioner: `driver.longhorn.io`
- OpenShift provisioner: `topolvm.io`
- OpenShift device class: `vg1`

OpenShift local LVM is node-local storage. It is not equivalent to Longhorn
replication and must not be described as node-failure resilient.

### NFS And SMB

The NFS and SMB CSI definitions are shared bases:

```text
manifests/infra/csi-driver-nfs/base
manifests/infra/csi-driver-smb/base
```

Both clusters have overlays and Argo metadata for these drivers. Existing
storage-class and static-PV names stay explicit because they identify real
TrueNAS shares and datasets.

Verify network reachability and OpenShift SCC compatibility before live sync.

## Backup Boundary

Talos currently owns the app PVC backup implementation:

- pvc-plumber labels
- VolSync privileged-mover namespace policy
- restore policy labels
- restore `dataSourceRef`

OpenShift overlays remove that policy. OpenShift app PVCs currently have no
equivalent GitOps backup guarantee. Treat backup/restore as unresolved until an
OpenShift-specific policy is selected and tested.

## App Readiness

An app is OpenShift-renderable when:

- it has an overlay under `clusters/openshift/apps`;
- its route uses the OpenShift Gateway and domain;
- Talos backup policy is absent from its OpenShift render;
- required security-context fields are compatible or explicitly patched.

An app is OpenShift-production-ready only after verifying:

- storage capacity and access mode;
- SCC behavior;
- external storage reachability;
- application callback/base URLs;
- backup and restore expectations.

Large stateful apps remain compatibility-test candidates until those checks are
complete.

Catalog migration does not override existing activation state. DVWA and Project
Nomad's Kolibri resources remain intentionally disabled in both clusters.

## Live Schema Assumptions

Verify these against the intended OpenShift cluster:

- `LVMCluster` API and `stable-4.20` Subscription channel;
- TopoLVM provisioner name `topolvm.io`;
- device-class parameter `topolvm.io/device-class: vg1`;
- NFS and SMB CSI chart SCC requirements;
- GatewayClass name `openshift-default`.
