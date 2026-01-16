# Testing k8s-admin Unified Authentication

## Prerequisites

### 1. Update 1Password Item
Ensure the `rustfs` item in 1Password has these exact fields:

```
Item: rustfs
├─ k8s-admin-access-key: "k8s-admin"
├─ k8s-admin-secret-key: "<secret from RustFS console>"
├─ restic_password: "<restic encryption password>"
└─ restic_repository: "s3:http://192.168.10.133:30292/volsync-backup/"
```

**Action Required:**
1. Open 1Password
2. Find the `rustfs` item
3. Add/rename fields:
   - `k8s-admin-access-key` → value should be `k8s-admin`
   - `k8s-admin-secret-key` → copy the secret key from RustFS console
4. Save the item

---

## Testing Plan

### Phase 1: Verify ExternalSecrets Sync

After committing changes and ArgoCD syncs (or manual apply):

```bash
# Check ExternalSecret status in volsync-system
kubectl get externalsecret -n volsync-system
kubectl describe externalsecret volsync-s3-credentials -n volsync-system

# Expected: Status should show "SecretSynced: True"
# If error: Check that 1Password has the k8s-admin-access-key field

# Verify the generated secret has correct keys
kubectl get secret volsync-s3-credentials -n volsync-system -o yaml

# Should contain:
#   AWS_ACCESS_KEY_ID: <base64 of "k8s-admin">
#   AWS_SECRET_ACCESS_KEY: <base64 of secret>
```

```bash
# Check ClusterExternalSecret for volsync-rustfs-base
kubectl get clusterexternalsecret volsync-rustfs-base
kubectl describe clusterexternalsecret volsync-rustfs-base

# Check generated secrets in labeled namespaces
kubectl get secret volsync-rustfs-base -n karakeep -o yaml
kubectl get secret volsync-rustfs-base -n open-webui -o yaml

# Decode and verify AWS_ACCESS_KEY_ID = "k8s-admin"
kubectl get secret volsync-rustfs-base -n karakeep -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
# Expected output: k8s-admin
```

```bash
# Check Longhorn credentials
kubectl get externalsecret -n longhorn-system
kubectl describe externalsecret longhorn-backup-credentials -n longhorn-system

kubectl get secret longhorn-backup-credentials -n longhorn-system -o yaml
# Should contain AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
```

```bash
# Check monitoring stack credentials
kubectl get externalsecret -n loki-stack
kubectl get externalsecret -n monitoring  # for tempo

kubectl get secret loki-s3-credentials -n loki-stack -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
# Expected: k8s-admin

kubectl get secret tempo-s3-credentials -n monitoring -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
# Expected: k8s-admin
```

```bash
# Check database backup credentials
kubectl get externalsecret -n cloudnative-pg
kubectl get secret cnpg-s3-credentials -n cloudnative-pg -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
# Expected: k8s-admin

kubectl get externalsecret -n crunchy-postgres
kubectl get secret pgo-s3-credentials -n crunchy-postgres -o jsonpath='{.data}' | jq
```

---

### Phase 2: Test VolSync Backups

```bash
# Check existing ReplicationSources
kubectl get replicationsource -A

# Pick one that already exists (e.g., karakeep/meilisearch-pvc-backup)
kubectl describe replicationsource meilisearch-pvc-backup -n karakeep

# Look for:
# - Status.Conditions: Type=Synchronizing, Status=True
# - Status.LastSyncTime: should be recent
# - Events: should show successful sync

# Trigger manual backup (if schedule hasn't run yet)
kubectl patch replicationsource meilisearch-pvc-backup -n karakeep \
  --type=merge -p '{"spec":{"trigger":{"manual":"test-'$(date +%s)'"}}}'

# Watch for backup job to start
kubectl get jobs -n karakeep -w

# Check logs of backup job
kubectl logs -n karakeep -l volsync.backube/replication-source=meilisearch-pvc-backup --tail=50

# Expected: Should show Restic connecting to S3, uploading data, no auth errors
```

#### Create Test PVC and Backup

```bash
# Create test namespace
kubectl create namespace volsync-test
kubectl label namespace volsync-test volsync.backube/privileged-movers=true

# Wait for ExternalSecret to sync
sleep 10
kubectl get secret volsync-rustfs-base -n volsync-test

# Create test PVC with backup label
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-backup-pvc
  namespace: volsync-test
  labels:
    backup: "hourly"
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF

# Write some test data
kubectl run test-writer --image=busybox --restart=Never -n volsync-test \
  --overrides='{"spec":{"containers":[{"name":"test","image":"busybox","command":["sh","-c","echo \"Test data at $(date)\" > /data/test.txt && sleep 3600"],"volumeMounts":[{"name":"data","mountPath":"/data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"test-backup-pvc"}}]}}'

# Wait for pod to write data
sleep 5
kubectl logs test-writer -n volsync-test

# Check if Kyverno generated ReplicationSource
kubectl get replicationsource -n volsync-test
# Expected: test-backup-pvc-backup should exist

# Describe it to see status
kubectl describe replicationsource test-backup-pvc-backup -n volsync-test

# Check Kyverno events on PVC
kubectl describe pvc test-backup-pvc -n volsync-test
# Should show events from kyverno about generating ReplicationSource

# Wait for next hour boundary or trigger manual backup
kubectl patch replicationsource test-backup-pvc-backup -n volsync-test \
  --type=merge -p '{"spec":{"trigger":{"manual":"test-'$(date +%s)'"}}}'

# Watch backup job
kubectl get jobs -n volsync-test -w

# Check job logs
kubectl logs -n volsync-test -l volsync.backube/replication-source=test-backup-pvc-backup -f
```

**Expected Success Indicators:**
- ReplicationSource shows `Synchronizing: True`
- Job completes successfully
- Logs show Restic uploading to S3 without auth errors
- Check RustFS console: `volsync-backup/volsync-test/test-backup-pvc/` should have data

**Common Errors:**
- `Access Denied` → k8s-admin-secret-key is wrong in 1Password
- `Secret not found` → ExternalSecret hasn't synced yet
- `Repository does not exist` → First backup will init repo (normal)

---

### Phase 3: Test Longhorn Backups

```bash
# Check Longhorn backup target configuration
kubectl get setting -n longhorn-system backup-target -o yaml

# Should show: s3://longhorn@... with credentials from secret

# Trigger test backup of a Longhorn volume
# Find a volume to test with
kubectl get volumes -n longhorn-system

# Create backup via Longhorn UI or kubectl
# (Longhorn backups are typically done via UI or custom scripts)

# Alternative: Check if existing backups are accessible
# Login to Longhorn UI and go to Backup tab
# Expected: Should be able to see existing backups without auth errors
```

---

### Phase 4: Test Monitoring Stack S3 Access

```bash
# Check Loki is writing to S3 (chunks storage)
kubectl logs -n loki-stack -l app.kubernetes.io/name=loki --tail=50 | grep -i s3

# Should NOT see auth errors like:
# - "Access Denied"
# - "InvalidAccessKeyId"

# Check Tempo is writing to S3 (traces storage)
kubectl logs -n monitoring -l app.kubernetes.io/name=tempo --tail=50 | grep -i s3
```

---

### Phase 5: Test Database Backups

```bash
# Check CloudNativePG backups
kubectl get backups -n cloudnative-pg
kubectl describe backup <backup-name> -n cloudnative-pg

# Check Crunchy Postgres backups
kubectl get postgrescluster -n crunchy-postgres immich -o yaml | grep -A 10 backup

# Trigger manual backup
kubectl annotate postgrescluster immich -n crunchy-postgres \
  postgres-operator.crunchydata.com/pgbackrest-backup="$(date +%Y-%m-%d-%H-%M-%S)"

# Check backup job logs
kubectl logs -n crunchy-postgres -l postgres-operator.crunchydata.com/pgbackrest-backup --tail=100
```

---

## Cleanup Test Resources

```bash
# Remove test PVC and namespace
kubectl delete pod test-writer -n volsync-test
kubectl delete pvc test-backup-pvc -n volsync-test
kubectl delete replicationsource test-backup-pvc-backup -n volsync-test
kubectl delete namespace volsync-test
```

---

## Rollback Plan (If Something Breaks)

If authentication fails, you can quickly rollback:

### Option 1: Revert 1Password (Quick Fix)
1. Rename fields back to old names temporarily:
   - `k8s-admin-access-key` → `access_key` (or `loki_access_key` for monitoring)
   - `k8s-admin-secret-key` → `secret_key` (or `loki` for monitoring)
2. Wait 1 hour for ExternalSecrets to refresh, or force sync:
   ```bash
   kubectl annotate externalsecret volsync-s3-credentials -n volsync-system \
     force-sync=$(date +%s) --overwrite
   ```

### Option 2: Revert Git Changes
```bash
git revert HEAD
git push
# ArgoCD will auto-sync back to old config
```

### Option 3: Manual Secret Override (Emergency)
```bash
# Manually create secret with correct credentials
kubectl create secret generic volsync-s3-credentials \
  -n volsync-system \
  --from-literal=AWS_ACCESS_KEY_ID=k8s-admin \
  --from-literal=AWS_SECRET_ACCESS_KEY='<actual-secret>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## Success Criteria Checklist

- [ ] All ExternalSecrets show `SecretSynced: True`
- [ ] Secrets contain `AWS_ACCESS_KEY_ID=k8s-admin` (decoded)
- [ ] VolSync test backup completes successfully
- [ ] No S3 authentication errors in any component logs
- [ ] RustFS console shows new backup data in test namespace
- [ ] Longhorn backup target accessible in UI
- [ ] Loki and Tempo logs show no S3 errors
- [ ] Database backup jobs complete successfully

Once all checkboxes are ✅, the k8s-admin unified authentication is working!
