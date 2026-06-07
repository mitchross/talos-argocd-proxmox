# TrueNAS CSI NFS Canary

The canary is manual and excluded from the Argo CD application. Run it only
after the `truenas-csi` Application is Healthy and 1Password item
`truenas-csi` contains field `apiKey` for a dedicated TrueNAS service account.
On TrueNAS 26, grant that account `SHARING_ADMIN` plus the snapshot roles
needed by `pool.snapshot.*` and `pool.snapshottask.*`; do not reuse a root or
full-admin key.

## Preconditions

```bash
kubectl get application truenas-csi -n argocd
kubectl get pods -n truenas-csi -o wide
kubectl get csidriver csi.truenas.io
kubectl get storageclass truenas-nfs
kubectl get externalsecret,secret -n truenas-csi truenas-api-credentials
```

The node DaemonSet must be Ready on every schedulable node before continuing.

## Provision And Mount

```bash
kubectl apply -f infrastructure/storage/truenas-csi/canary/nfs-canary.yaml
kubectl wait -n truenas-csi-canary \
  --for=jsonpath='{.status.phase}'=Bound pvc/truenas-nfs-canary \
  --timeout=2m
kubectl get pod,pvc -n truenas-csi-canary -o wide
```

The three pods use required pod anti-affinity, so they should land on separate
nodes.

## Ownership Gate

```bash
kubectl logs -n truenas-csi-canary truenas-nfs-root-writer
kubectl logs -n truenas-csi-canary truenas-nfs-nonroot-writer
kubectl logs -n truenas-csi-canary truenas-nfs-reader
kubectl get pod -n truenas-csi-canary truenas-nfs-nonroot-writer \
  -o jsonpath='{.status.phase}{"\n"}'
```

The non-root writer must remain `Running` and report ownership `1000:1000`.
TrueNAS CSI v1.0.4 uses NFS `mapall` and may instead report `0:0`. Treat that
as a failed compatibility gate for workloads that require UID/GID
preservation. Do not normalize the result by running the application as root
without explicitly accepting that security change.

## Expansion

```bash
kubectl patch pvc truenas-nfs-canary -n truenas-csi-canary \
  --type merge -p '{"spec":{"resources":{"requests":{"storage":"2Gi"}}}}'
kubectl wait -n truenas-csi-canary \
  --for=jsonpath='{.status.capacity.storage}'=2Gi pvc/truenas-nfs-canary \
  --timeout=2m
```

Confirm the dataset refquota is 2 GiB in TrueNAS.

## Snapshot And Clone

```bash
kubectl apply -f - <<'EOF'
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: truenas-nfs-canary
  namespace: truenas-csi-canary
spec:
  volumeSnapshotClassName: truenas-snapshot
  source:
    persistentVolumeClaimName: truenas-nfs-canary
EOF

kubectl wait -n truenas-csi-canary \
  --for=jsonpath='{.status.readyToUse}'=true \
  volumesnapshot/truenas-nfs-canary --timeout=2m

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: truenas-nfs-canary-clone
  namespace: truenas-csi-canary
  labels:
    backup-exempt: "true"
  annotations:
    storage.vanillax.dev/backup-exempt-reason: "Disposable TrueNAS CSI snapshot clone validation volume"
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: truenas-nfs
  dataSource:
    name: truenas-nfs-canary
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
  resources:
    requests:
      storage: 2Gi
EOF
```

Mount the clone in a temporary pod and verify `root-writer.txt` and
`nonroot-writer.txt` contain the expected data.

## Cleanup And Retained PVs

The StorageClass and snapshot class both use `Retain`. Deleting the namespace
does not delete the TrueNAS datasets or snapshots.

```bash
kubectl get pvc -n truenas-csi-canary -o jsonpath='{range .items[*]}{.spec.volumeName}{"\n"}{end}'
kubectl get volumesnapshotcontent \
  -o custom-columns=NAME:.metadata.name,SNAPSHOT:.spec.volumeSnapshotRef.name,HANDLE:.status.snapshotHandle
kubectl delete namespace truenas-csi-canary
kubectl get pv | grep truenas-nfs
```

For each retained PV, verify the corresponding dataset and snapshot in
TrueNAS, delete them deliberately, then delete the released Kubernetes PV and
VolumeSnapshotContent objects.

## Rollback

If provisioning, ownership, expansion, snapshot, or clone validation fails:

1. Do not move application PVCs to `truenas-nfs`.
2. Capture controller and node logs.
3. Delete the canary namespace and manually clean retained backend objects.
4. Revert the `truenas-csi` AppSet path before removing the driver.
