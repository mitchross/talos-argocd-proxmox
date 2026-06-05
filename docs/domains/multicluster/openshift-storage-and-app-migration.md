# OpenShift Storage And App Migration Strategy

## Plain-English Summary

OpenShift receives the same app catalog through its own overlays, but it does
not inherit Talos infrastructure or backup behavior.

Small local PVCs use the portable `vanillax-local-rwo` contract. Talos backs
that contract with Longhorn; OpenShift backs it with LVM Storage. Large or
shared datasets continue to use explicit NFS, SMB, or static PV definitions.

> **Live status:** The OpenShift LVM implementation is intended but not
> currently available on `sno-ai-lab`. The June 4, 2026 read-only audit found
> an unresolved `lvms-operator` Subscription and no LVM CRD, TopoLVM API, or
> StorageClass. Do not describe `vanillax-local-rwo` as implemented on the
> live OpenShift cluster yet.

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

### Portable Platform Services

The byte-identical `1passwordconnect`, `cert-manager`, and `external-secrets`
definitions are shared bases under `manifests/infra`. OpenShift retains
cluster-owned entrypoints that consume those bases.

## Gateway API

OpenShift uses the platform Ingress Operator Gateway API implementation. Git
declares GatewayClass `openshift-default` with controller
`openshift.io/gateway-controller/v1`, then declares the shared Gateway in
`openshift-ingress`.

The OpenShift bootstrap profile verifies the platform-owned Gateway API CRDs
and rejects a conflicting Service Mesh Operator v2 subscription. It never
installs Cilium or upstream Gateway API CRDs.

Default OpenShift Routes keep `*.apps.sno-ai-lab.vanillax.xyz` on the
HostNetwork router for console, OAuth, and ordinary Route traffic. GitOps
HTTPRoutes use `*.gateway.apps.sno-ai-lab.vanillax.xyz` through the shared
Gateway in `openshift-ingress`.

Git now declares MetalLB for the platform-None SNO LoadBalancer path:

- operator namespace/subscription: `clusters/openshift/infra/metallb-operator`
- address pool and L2 advertisement: `clusters/openshift/infra/metallb-config`
- pool: `192.168.10.230-192.168.10.240`

The old `openshift-sno-lab` reference repo used this same split-domain pattern:
default `*.apps` on the OpenShift router IP and `*.gateway.apps` on MetalLB.
Do not treat the new manifests as live-proven until the MetalLB channel
resolves on `4.22.0-rc.5`, `.230` is reachable, and authoritative DNS resolves
Gateway names to `.230`.

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

## Live Schema Status

Verified against the intended OpenShift cluster:

- OpenShift is `4.22.0-rc.5`, channel `stable-4.22`.
- Gateway API CRDs are installed; no conflicting Service Mesh Operator v2
  subscription was found.
- GatewayClass controller behavior has not been activated or tested.
- The existing `lvms-operator` Subscription is unresolved; `stable-4.20`,
  `LVMCluster`, TopoLVM, device class `vg1`, and
  `vanillax-local-rwo` are not live-proven.

Still verify NFS/SMB CSI SCC requirements, application SCC behavior, external
storage reachability, and the eventual Gateway LoadBalancer path.
