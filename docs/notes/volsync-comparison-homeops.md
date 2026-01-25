# VolSync Implementation Comparison: Our Approach vs home-ops (onedr0p)

**Date:** 2026-01-24
**Purpose:** Reference for potential future reimplementation or improvements

## Summary

Our Kyverno + pvc-plumber approach is architecturally superior for DRY and ease of use. home-ops has better polish (monitoring, UI, Kopia speed). This note captures the full analysis.

---

## Our Approach

### Architecture
- **Policy Engine:** Kyverno ClusterPolicy
- **Backup Engine:** Restic (could migrate to Kopia)
- **Storage Backend:** S3 (TrueNAS RustFS)
- **Restore Detection:** pvc-plumber service (S3 HEAD request)
- **Opt-in Mechanism:** Label on PVC (`backup: "hourly"` or `backup: "daily"`)

### How It Works
1. Add `backup: "hourly"` label to any PVC
2. Kyverno policy triggers on PVC CREATE
3. pvc-plumber checks S3 for existing backup
4. Kyverno generates: ExternalSecret, ReplicationSource, ReplicationDestination
5. If backup exists, PVC gets `dataSourceRef` for auto-restore

### Key Files
- `infrastructure/controllers/kyverno/policies/volsync-pvc-backup-restore.yaml`
- `infrastructure/controllers/pvc-plumber/deployment.yaml`
- `infrastructure/storage/volsync/`

### Strengths
- **Zero per-app configuration** - just add a label
- **Conditional restore** - fresh clusters start empty, DR restores data
- **GitOps-agnostic** - works with ArgoCD, Flux, or anything
- **Per-PVC repository isolation** - each PVC gets its own Restic repo
- **S3 backend** - portable, resilient

### Weaknesses
- Restic is slower than Kopia
- No backup UI
- No Prometheus alerts/Grafana dashboards
- No maintenance jobs for repository cleanup

---

## home-ops Approach (onedr0p)

### Architecture
- **Policy Engine:** Kustomize Components + MutatingAdmissionPolicy
- **Backup Engine:** Kopia
- **Storage Backend:** NFS (single server: `expanse.internal:/mnt/eros/VolsyncKopia`)
- **Restore Detection:** None (always tries to restore via `IfNotPresent` label)
- **Opt-in Mechanism:** Include component in Flux Kustomization

### How It Works
1. Each app's `ks.yaml` includes the volsync component:
   ```yaml
   spec:
     components:
       - ../../../../components/volsync
     postBuild:
       substitute:
         APP: sonarr
         VOLSYNC_CAPACITY: 5Gi
   ```
2. Component generates: ExternalSecret, PVC, ReplicationSource, ReplicationDestination
3. MutatingAdmissionPolicy injects NFS volume into VolSync mover jobs
4. MutatingAdmissionPolicy adds jitter (0-30s random sleep) to prevent backup storms

### Key Files (in home-ops/)
- `kubernetes/components/volsync/` - Kustomize component
- `kubernetes/apps/volsync-system/volsync/app/mutatingadmissionpolicy.yaml` - Job injection
- `kubernetes/apps/volsync-system/volsync/maintenance/` - Repository maintenance
- `kubernetes/apps/volsync-system/kopia/` - Kopia Web UI

### Strengths
- Kopia is faster (parallel, better compression)
- Kopia Web UI for browsing backups
- Prometheus alerts for out-of-sync volumes
- Grafana dashboard
- Repository maintenance jobs (KopiaMaintenance)
- Jitter prevents backup storms

### Weaknesses
- **DRY violation** - every app needs ~10 lines in ks.yaml
- **No conditional restore** - may fail on fresh clusters
- **Flux-specific** - tied to Flux Kustomizations
- **NFS dependency** - single point of failure

---

## Feature Comparison

| Feature | Our Solution | home-ops | Winner |
|---------|-------------|----------|--------|
| Lines of YAML per app | 1 (label) | ~10 (component + vars) | **Ours** |
| Conditional restore | Yes | No | **Ours** |
| Fresh cluster behavior | Works | May fail | **Ours** |
| Backup engine speed | Restic (slower) | Kopia (faster) | home-ops |
| Backup UI | None | Kopia Web UI | home-ops |
| Monitoring | None | Prometheus + Grafana | home-ops |
| Repository maintenance | None | KopiaMaintenance | home-ops |
| Jitter for scheduling | None | MutatingAdmissionPolicy | home-ops |
| GitOps tool independence | Yes | No (Flux-specific) | **Ours** |

---

## Improvements We Could Adopt

### 1. Switch to Kopia (instead of Restic)
Change `restic:` to `kopia:` in Kyverno policy. Kopia supports S3 natively.

### 2. Add Prometheus Alerts
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
spec:
  groups:
    - name: volsync.rules
      rules:
        - alert: VolSyncVolumeOutOfSync
          expr: volsync_volume_out_of_sync == 1
          for: 5m
          labels:
            severity: critical
```

### 3. Add Grafana Dashboard
home-ops has one at `volsync-system/volsync/app/grafanadashboard.yaml`

### 4. Add Repository Maintenance
Generate KopiaMaintenance jobs (or use Restic `prune` commands via CronJob)

### 5. Jitter (Optional)
Add MutatingAdmissionPolicy to inject random sleep into VolSync jobs. Less relevant for single-node clusters.

---

## home-ops Useful Commands (from mod.just)

```bash
# Manual snapshot all PVCs
kubectl get replicationsources --no-headers -A | while read -r ns name _; do
    kubectl -n "$ns" patch replicationsources "$name" --type merge \
        -p '{"spec":{"trigger":{"manual":"'$(date +%s)'"}}}'
done

# Browse a PVC (requires kubectl-browse-pvc plugin)
kubectl browse-pvc -n <namespace> -i alpine:latest <claim>

# Suspend VolSync (for maintenance)
kubectl -n volsync-system scale deployment volsync --replicas 0
```

---

## Decision Record

**2026-01-24:** After thorough comparison, our label-driven Kyverno approach is preferred for:
- Simpler developer experience (just add a label)
- True conditional restore (pvc-plumber checks S3)
- GitOps tool independence

Future improvements: Consider Kopia migration for speed, add monitoring.
