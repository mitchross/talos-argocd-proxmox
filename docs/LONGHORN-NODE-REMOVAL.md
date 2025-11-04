# Longhorn Node Removal Procedure

## Problem You Experienced

When nodes `talos-blj-72f` and `talos-kyk-7ek` were removed from your cluster without proper Longhorn evacuation:

1. **40+ volumes became faulted** because they had replicas on the removed nodes
2. **PVCs stuck in Terminating state** due to finalizers
3. **Applications couldn't start** (Prometheus, Loki, Gitea)
4. **Manual intervention required** to patch PVCs and delete pods

## Root Causes Fixed

### 1. Configuration Changes Applied

#### Added `node-failure-settings.yaml`:
- `node-down-pod-deletion-policy`: Changed from `do-nothing` to `delete-both-statefulset-and-deployment-pod`
- `orphan-auto-deletion`: Enabled to automatically clean up orphaned data
- `storage-reserved-percentage-default`: Increased from 10% to 25%

#### Updated `values.yaml`:
- `storageMinimalAvailablePercentage`: 10% → 25%

These changes are in Git and will be applied by ArgoCD on next sync.

---

## PROPER Node Removal Procedure

**ALWAYS follow these steps BEFORE removing a node from Kubernetes!**

### Step 1: Check Node Health in Longhorn

```bash
# View Longhorn node status
kubectl get nodes.longhorn.io -n longhorn-system

# Check replica distribution on the node you want to remove
NODE_NAME="talos-xyz-abc"  # Replace with actual node name
kubectl get nodes.longhorn.io $NODE_NAME -n longhorn-system \
  -o jsonpath='{.status.diskStatus.*.scheduledReplica}' | jq
```

### Step 2: Disable Scheduling on the Node

This prevents new replicas from being scheduled to the node:

```bash
kubectl patch node.longhorn.io $NODE_NAME -n longhorn-system \
  --type=merge -p '{"spec":{"allowScheduling":false}}'
```

Verify:
```bash
kubectl get nodes.longhorn.io $NODE_NAME -n longhorn-system | grep -i schedulable
```

### Step 3: Request Replica Eviction

This migrates all replicas off the node:

```bash
kubectl patch node.longhorn.io $NODE_NAME -n longhorn-system \
  --type=merge -p '{"spec":{"evictionRequested":true}}'
```

### Step 4: Monitor Replica Migration

**This is critical** - wait for ALL replicas to migrate:

```bash
# Watch the migration process
watch kubectl get nodes.longhorn.io $NODE_NAME -n longhorn-system

# Check scheduled replica count (should become 0)
kubectl get nodes.longhorn.io $NODE_NAME -n longhorn-system \
  -o jsonpath='{.status.diskStatus.*.scheduledReplica}' | jq '. | length'

# View migration progress for all volumes
kubectl get volumes -n longhorn-system \
  -o jsonpath='{range .items[?(@.status.kubernetesStatus.lastPodRefAt!="")]}{.metadata.name}{"\t"}{.status.robustness}{"\n"}{end}'
```

**Wait until:**
- Scheduled replica count = 0
- All volumes show `robustness: healthy`
- No replica rebuilding in progress

This may take **10-30 minutes** depending on data size.

### Step 5: Remove Node from Longhorn

Only after ALL replicas are migrated:

```bash
kubectl delete node.longhorn.io $NODE_NAME -n longhorn-system
```

### Step 6: Drain and Remove Kubernetes Node

Now it's safe to remove the node from Kubernetes:

```bash
# Drain the node (this will evict all pods)
kubectl drain $NODE_NAME --ignore-daemonsets --delete-emptydir-data --timeout=10m

# Verify no pods are running (except DaemonSets)
kubectl get pods --all-namespaces --field-selector spec.nodeName=$NODE_NAME

# Delete the node
kubectl delete node $NODE_NAME
```

### Step 7: Verify Cluster Health

```bash
# Check all nodes
kubectl get nodes

# Verify all volumes are healthy
kubectl get volumes -n longhorn-system | grep -v healthy

# Check for any faulted volumes (should be none)
kubectl get volumes -n longhorn-system | grep faulted
```

---

## Emergency Recovery (If Node Already Removed)

If you've already removed a node and have faulted volumes:

### 1. Identify Faulted Volumes

```bash
kubectl get volumes -n longhorn-system -o json | \
  jq -r '.items[] | select(.status.robustness=="faulted") |
  {name: .metadata.name, state: .status.state, pv: .status.kubernetesStatus.pvName}'
```

### 2. For Detached Faulted Volumes (Safe to Delete)

```bash
# List them
kubectl get volumes -n longhorn-system -o json | \
  jq -r '.items[] | select(.status.state=="detached" and .status.robustness=="faulted") | .metadata.name'

# Delete them (they're not in use)
for vol in $(kubectl get volumes -n longhorn-system -o json | \
  jq -r '.items[] | select(.status.state=="detached" and .status.robustness=="faulted") | .metadata.name'); do
  echo "Deleting faulted volume: $vol"
  kubectl delete volume $vol -n longhorn-system
done
```

### 3. For Attached Faulted Volumes (More Complex)

These require manual intervention:

```bash
# Find the PVC using the volume
PV_NAME="pvc-xxxxx"
kubectl get pvc -A -o json | \
  jq -r '.items[] | select(.spec.volumeName=="'$PV_NAME'") |
  {namespace: .metadata.namespace, name: .metadata.name, status: .status.phase}'
```

If PVC is `Terminating`:

```bash
# Remove finalizers
kubectl patch pvc <pvc-name> -n <namespace> \
  -p '{"metadata":{"finalizers":null}}' --type=merge

# Delete the pod using it
kubectl delete pod <pod-name> -n <namespace>
```

The pod will recreate with a new PVC.

---

## Monitoring and Alerting

### Check Longhorn Health Regularly

Add this to your maintenance routine:

```bash
#!/bin/bash
# longhorn-health-check.sh

echo "=== Longhorn Nodes ==="
kubectl get nodes.longhorn.io -n longhorn-system

echo -e "\n=== Faulted Volumes ==="
kubectl get volumes -n longhorn-system | grep faulted || echo "None"

echo -e "\n=== Degraded Volumes ==="
kubectl get volumes -n longhorn-system | grep degraded || echo "None"

echo -e "\n=== Storage Capacity ==="
kubectl get nodes.longhorn.io -n longhorn-system \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.diskStatus.*.storageAvailable}{"\t/\t"}{.status.diskStatus.*.storageMaximum}{"\n"}{end}' | \
  awk '{printf "%s\t%.2f GB / %.2f GB\n", $1, $2/1e9, $4/1e9}'
```

### Prometheus Alerts

Your [monitoring/prometheus-stack/longhorn-backup-alerts.yaml](../monitoring/prometheus-stack/longhorn-backup-alerts.yaml) should include:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: longhorn-health-alerts
  namespace: prometheus-stack
  labels:
    release: kube-prometheus-stack
spec:
  groups:
    - name: longhorn.health
      interval: 30s
      rules:
        - alert: LonghornVolumeFaulted
          expr: longhorn_volume_robustness == 3
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "Longhorn volume {{ $labels.volume }} is faulted"
            description: "Volume has been in faulted state for 5 minutes - data may be lost"

        - alert: LonghornNodeDown
          expr: longhorn_node_status{condition="ready"} == 0
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "Longhorn node {{ $labels.node }} is down"
            description: "Check node health and migrate replicas if needed"

        - alert: LonghornDiskSpaceLow
          expr: (longhorn_node_storage_usage_bytes / longhorn_node_storage_capacity_bytes) > 0.75
          for: 15m
          labels:
            severity: warning
          annotations:
            summary: "Longhorn disk space low on {{ $labels.node }}"
            description: "Disk usage is above 75% - consider adding storage or cleaning up"
```

---

## Best Practices Summary

### DO:
✅ Always disable scheduling before removing a node
✅ Request eviction and wait for migration to complete
✅ Monitor replica migration progress
✅ Verify all volumes are healthy before final removal
✅ Keep at least 25% free space on Longhorn disks
✅ Use replica count of 3 for critical data (already configured)
✅ Test your backup/restore procedures regularly

### DON'T:
❌ Remove a Kubernetes node without evacuating Longhorn first
❌ Force delete nodes with `kubectl delete node --force`
❌ Ignore faulted or degraded volumes
❌ Let disk space drop below 25% available
❌ Skip the monitoring step during migration

---

## Your Current Configuration

**Replica Count:** 3 (good for resilience)
**Storage Reserved:** 25% (prevents "insufficient storage" errors)
**Auto-balance:** best-effort (distributes replicas evenly)
**Node Down Policy:** delete-both-statefulset-and-deployment-pod (auto-recovery)
**Orphan Auto-Delete:** true (cleans up stuck PVCs)

These settings are now in your Git repo and will be applied automatically.

---

## Quick Reference

```bash
# Check if node is safe to remove
kubectl get nodes.longhorn.io <node> -n longhorn-system -o jsonpath='{.status.diskStatus.*.scheduledReplica}' | jq '. | length'

# If output is 0, node is empty and safe to remove
# If output is > 0, follow the evacuation procedure above
```

**Remember:** Patience during replica migration saves hours of recovery work!
