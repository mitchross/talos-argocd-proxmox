Add automatic backup to PVC(s) in `$ARGUMENTS`.

Use the shipped pvc-plumber `v4.0.1` contract. pvc-plumber owns VolSync
`ReplicationSource` and `ReplicationDestination` resources. VolSync/Kopia move
bytes. Do not add inline RS/RD documents for normal application PVCs.

## Steps

1. Identify the normal application PVCs that need protection.
2. Confirm each shared app PVC uses `storageClassName: vanillax-local-rwo`.
   Talos maps that portable class to Longhorn. This backup workflow is Talos
   policy and is removed by OpenShift overlays.
3. Add the namespace software gate:

   ```yaml
   metadata:
     labels:
       pvc-plumber.io/managed-namespace: "true"
       volsync.backube/privileged-movers: "true"
   ```

4. Add the PVC fuse labels and static restore reference:

   ```yaml
   metadata:
     labels:
       pvc-plumber.io/enabled: "true"
       pvc-plumber.io/manage-volsync: "true"
       pvc-plumber.io/tier: daily
   spec:
     dataSourceRef:
       apiGroup: volsync.backube
       kind: ReplicationDestination
       name: <pvc-name>-dst
   ```

5. Keep the static `dataSourceRef`. Without it, a recreated PVC comes back
   empty even if backups exist.
6. Sync through GitOps and verify the operator-owned resources:

   ```bash
   kubectl get secret,replicationsource,replicationdestination -n <namespace>
   kubectl port-forward -n pvc-plumber svc/pvc-plumber 8080:8080
   curl -fsS http://127.0.0.1:8080/audit
   ```

## Exclusions

Do not generic-migrate:

- CNPG PVCs. CNPG uses native Barman/S3.
- Redis PVCs. Redis is backup-exempt and disposable.
- PostHog PVCs. PostHog is backup-exempt and disposable.
- System namespace PVCs.
- PVCs that do not resolve to the Talos Longhorn snapshot path.

For intentionally disposable PVCs, use `backup-exempt: "true"` and the
fully-qualified `storage.vanillax.dev/backup-exempt-reason` annotation.

## References

- [`docs/pvc-plumber-start-here.md`](../../docs/pvc-plumber-start-here.md)
- [`docs/talos-argocd-pvc-plumber-integration.md`](../../docs/talos-argocd-pvc-plumber-integration.md)
- [`docs/volsync-storage-recovery.md`](../../docs/volsync-storage-recovery.md)
