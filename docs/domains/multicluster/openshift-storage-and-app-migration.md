# OpenShift Storage And App Migration Strategy

## Plain-English Summary

Talos remains the full homelab app cluster. OpenShift is additive and should not
blindly receive every stateful workload just because the folder layout can support
it.

All existing apps move into the new repo layout in one shot under Talos deploy
targets. OpenShift deploy targets are added intentionally, app by app or class by
class, based on storage fit.

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

That decision should be made before migrating AI or other large-data apps.

## Do Not Migrate Yet

Large stateful Talos apps should not receive OpenShift deploy targets until each
has a storage decision and SCC/security review.

Examples to gate before OpenShift deployment:

- media libraries
- image/video ML workloads with large model caches
- database-backed apps with large PVCs
- anything currently depending on Longhorn-specific behavior
- anything with backup/restore assumptions tied to Talos PVC plumbing

## Migration Rule

An app is OpenShift-eligible only after its deploy target states:

- storage class or NFS/PV strategy
- hostname under `*.apps.sno-ai-lab.vanillax.xyz`
- Gateway parentRef
- SCC/securityContext adjustments
- backup/restore expectation, or explicit "not backed up yet"

Until then, keep it Talos-only:

```text
manifests/apps/<category>/<app>/deploy-targets/talos/
```

Add OpenShift only when ready:

```text
manifests/apps/<category>/<app>/deploy-targets/openshift/
```

## TODO

- Decide whether OpenShift NFS should use the existing CSI NFS chart pattern or static PVs first.
- Add an OpenShift NFS deploy target if CSI is chosen.
- Inventory large PVC apps and tag each as local LVM, NFS, defer, or redesign.
- Add OpenShift deploy targets only for apps whose storage and SCC plan is explicit.
