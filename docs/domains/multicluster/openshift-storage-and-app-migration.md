# OpenShift Storage And App Migration Strategy

## Plain-English Summary

Talos remains the full homelab app cluster. OpenShift is additive, but it now
receives the full app catalog as first-pass deploy targets so the entire shape
can be tested through OpenShift Argo CD.

All existing apps move into the new repo layout in one shot under Talos deploy
targets. OpenShift deploy targets also exist for every app, but production
readiness is still app-by-app based on storage fit, SCC behavior, and backup
expectations.

## Storage Classes By Use

### Local OpenShift Storage

Use OpenShift local storage, currently represented by the LVM Storage Operator
starter manifests, for small OpenShift-native PVCs:

- small app config/data volumes
- controller scratch/state
- low-capacity utility apps
- workloads where SNO node locality is acceptable

This is expected to be fast and simple, but it is node-local. Treat it as local
cluster storage, not cross-cluster shared storage.

### NFS Storage

Use NFS for workloads that need larger shared data or model/media-style storage,
matching the existing Talos pattern for AI and large file workloads:

- AI model caches
- shared datasets
- media-like large files that are safe to mount from NFS
- workloads where the data should live outside the OpenShift node

OpenShift needs an explicit NFS implementation decision before broad adoption:

- reuse the existing CSI NFS chart pattern as an OpenShift deploy target, or
- use static NFS PVs for the first few workloads.

That decision should be made before expecting AI or other large-data apps to be
healthy on OpenShift.

## Present But Not Production-Ready Yet

Large stateful Talos apps have OpenShift deploy targets for catalog testing, but
should not be treated as ready until each has a storage decision and SCC/security
review.

Examples to gate before OpenShift deployment:

- media libraries
- image/video ML workloads with large model caches
- database-backed apps with large PVCs
- anything currently depending on Longhorn-specific behavior
- anything with backup/restore assumptions tied to Talos PVC plumbing

## Migration Rule

An app is OpenShift-testable when it has:

- an OpenShift deploy target
- hostname under `*.apps.sno-ai-lab.vanillax.xyz`
- Gateway parentRef
- first-pass SCC/securityContext adjustments where generated

An app is OpenShift-production-ready only after its deploy target or companion
docs state:

- storage class or NFS/PV strategy
- SCC/securityContext expectation
- backup/restore expectation, or explicit "not backed up yet"

## TODO

- Decide whether OpenShift NFS should use the existing CSI NFS chart pattern or static PVs first.
- Add an OpenShift NFS deploy target if CSI is chosen.
- Inventory large PVC apps and tag each as local LVM, NFS, defer, or redesign.
- Promote apps from OpenShift-testable to OpenShift-production-ready once storage, SCC, and backup behavior are explicit.
