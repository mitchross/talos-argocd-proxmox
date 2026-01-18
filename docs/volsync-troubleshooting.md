# VolSync Backup System Troubleshooting

## Architecture Overview

The backup system is **fully automatic** - no user intervention required:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AUTOMATIC BACKUP FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. User creates PVC with label: backup=hourly                              │
│                     ↓                                                        │
│  2. Kyverno ClusterPolicy detects labeled PVC                               │
│                     ↓                                                        │
│  3. Kyverno generates THREE resources automatically:                        │
│     ├── Secret (per-PVC S3 credentials + repo path)                        │
│     ├── ReplicationSource (hourly backup job)                              │
│     └── ReplicationDestination (one-time restore on PVC creation)          │
│                     ↓                                                        │
│  4. VolSync runs backup every hour (0 * * * *)                              │
│                     ↓                                                        │
│  5. Data stored in RustFS S3: volsync-backup/<namespace>/<pvc-name>         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Purpose | Location |
|-----------|---------|----------|
| Kyverno ClusterPolicy | Auto-generates VolSync resources | `infrastructure/controllers/kyverno/volsync-smart-restore.yaml` |
| VolSync Operator | Runs restic backup/restore jobs | `volsync-system` namespace |
| ClusterExternalSecret | Copies base S3 creds to namespaces | Creates `volsync-rustfs-base` secret |
| RustFS | S3-compatible backup storage | TrueNAS @ 192.168.10.133:30292 |

## Prerequisites

For automatic backups to work, a namespace needs:

1. **Label on namespace**: `volsync.backube/privileged-movers=true`
2. **Base secret present**: `volsync-rustfs-base` (created by ClusterExternalSecret)
3. **PVC label**: `backup=hourly`

## Quick Status Check

```bash
# Check all backup jobs
kubectl get replicationsource -A

# Check for stuck pods
kubectl get pods -A | grep volsync | grep -v Running | grep -v Completed

# Check Longhorn volume health
kubectl get volumes.longhorn.io -n longhorn-system -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUSTNESS:.status.robustness | grep -E "(faulted|unknown)"

# Check Kyverno policy status
kubectl get clusterpolicy volsync-smart-protection
```

## Known Issues & Solutions

### Issue 1: Kyverno JMESPath Function Error

**Symptom**: Per-PVC secrets not being generated

**Cause**: Invalid JMESPath function `concat()` - should be `join('', [...])`

**Fix Applied**: Changed in `volsync-smart-restore.yaml`:
```yaml
# WRONG
RESTIC_REPOSITORY: "{{ base64_encode(concat(...)) }}"

# CORRECT
RESTIC_REPOSITORY: "{{ base64_encode(join('', [base64_decode(baseSecret.RESTIC_REPOSITORY_BASE), request.object.metadata.namespace, '/', request.object.metadata.name])) }}"
```

**Verify**:
```bash
kubectl get secret -A | grep volsync-secret
# Should see <pvc-name>-volsync-secret in each namespace
```

---

### Issue 2: Longhorn Volumes Faulted After Mass Pod Restart

**Symptom**: VolSync pods stuck in `ContainerCreating`, error: `volume is not ready for workloads`

**Cause**: When all pods are killed simultaneously, Longhorn engines die unexpectedly and volumes enter faulted/unknown state

**Events showing this**:
```
Warning  DetachedUnexpectedly  Engine of volume pvc-xxx dead unexpectedly, setting v.Status.Robustness to faulted
```

**Solution Options**:

1. **Wait for auto-recovery** (Longhorn auto-salvage is enabled)
   ```bash
   # Monitor recovery
   watch kubectl get volumes.longhorn.io -n longhorn-system -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUSTNESS:.status.robustness
   ```

2. **Force delete faulted volumes** (if they're VolSync cache volumes)
   ```bash
   # Delete faulted Longhorn volumes (cache/restore PVCs only!)
   for vol in $(kubectl get volumes.longhorn.io -n longhorn-system -o json | jq -r '.items[] | select(.status.robustness == "faulted") | .metadata.name'); do
     echo "Deleting: $vol"
     kubectl delete volume.longhorn.io $vol -n longhorn-system
   done
   ```

3. **Trigger re-evaluation** by annotating PVCs
   ```bash
   kubectl annotate pvc <pvc-name> -n <namespace> kyverno.io/trigger="$(date +%s)" --overwrite
   ```

---

### Issue 3: ReplicationDestination Pods Stuck

**Symptom**: `volsync-dst-*-restore-*` pods stuck in ContainerCreating

**Cause**: Restore jobs try to create cache volumes which may conflict with existing ones or fail to provision

**Solution**: The restore jobs only matter for disaster recovery. Backups work independently.

```bash
# Delete stuck restore jobs (backups continue working)
kubectl delete replicationdestination -A --all

# Clean up orphaned restore PVCs
kubectl delete pvc -A -l volsync.backube/replicationdestination
```

---

### Issue 4: No Base Secret in Namespace

**Symptom**: Kyverno policy precondition fails, no resources generated

**Check**:
```bash
kubectl get secret volsync-rustfs-base -n <namespace>
```

**Cause**: Namespace missing label for ClusterExternalSecret

**Fix**:
```bash
kubectl label namespace <namespace> volsync.backube/privileged-movers=true
```

---

### Issue 5: Backup Never Runs

**Symptom**: ReplicationSource exists but LAST_SYNC is empty

**Check schedule**:
```bash
kubectl get replicationsource <name> -n <namespace> -o yaml | grep -A5 trigger
```

**Manual trigger**:
```bash
kubectl patch replicationsource <name> -n <namespace> --type merge -p '{"spec":{"trigger":{"manual":"'$(date +%s)'"}}}'
```

---

## Longhorn Settings Reference

Current settings that affect VolSync:

| Setting | Value | Impact |
|---------|-------|--------|
| `auto-salvage` | true | Automatically recovers faulted volumes |
| `default-replica-count` | 3 | Requires 3 nodes for full redundancy |
| `replica-soft-anti-affinity` | false | Replicas must be on different nodes |

## RustFS Bucket Structure

```
volsync-backup/
├── home-assistant/
│   └── config/           # Home Assistant config PVC
├── karakeep/
│   ├── data-pvc/         # Karakeep data
│   └── meilisearch-pvc/  # Karakeep search index
├── khoj/
│   └── config/
├── n8n/
│   └── data/
├── open-webui/
│   ├── data/
│   └── storage/
├── paperless-ngx/
│   ├── data/
│   └── media/
└── redis-instance/
    └── redis-master-0/
```

## Session Notes: 2026-01-18

### Problems Observed

1. **Kyverno policy had invalid JMESPath**: `concat()` doesn't exist, changed to `join('', [...])`

2. **Mass pod restart caused Longhorn volume faults**: After killing all pods, Longhorn engines died unexpectedly causing volumes to enter faulted/unknown state

3. **VolSync cache volumes stuck**: New PVCs for caches were created but couldn't attach due to Longhorn recovery state

### Current Status

| Namespace | PVC | Backup Status |
|-----------|-----|---------------|
| home-assistant | config | ✅ Working |
| karakeep | data-pvc | ✅ Working |
| karakeep | meilisearch-pvc | ✅ Working |
| khoj | config | ✅ Working |
| n8n | data | ✅ Working |
| open-webui | data | ✅ Working |
| open-webui | storage | ❌ Stuck (Longhorn recovery) |
| paperless-ngx | data | ❌ Stuck (Longhorn recovery) |
| paperless-ngx | media | ❌ Stuck (Longhorn recovery) |
| redis-instance | redis-master-0 | ❌ Stuck (Longhorn recovery) |
| volsync-test | volsync-test-data | ✅ Working |

### Files Modified

- `infrastructure/controllers/kyverno/volsync-smart-restore.yaml` - Fixed JMESPath function

### Next Steps

1. Monitor Longhorn volume recovery: `watch kubectl get volumes.longhorn.io -n longhorn-system | grep -E "(faulted|unknown)"`
2. Once volumes recover, stuck backups should auto-resume at next scheduled time
3. If volumes don't recover, delete faulted volumes and let Kyverno regenerate

### Root Cause Analysis

The VolSync/Kyverno system works correctly. The issues were:

1. **One-time bug**: JMESPath syntax error in Kyverno policy (now fixed)
2. **Transient issue**: Longhorn volume recovery after mass pod restart (will self-heal)

The system IS fully automatic when:
- Longhorn is healthy
- Kyverno is running
- Base secrets are in place
