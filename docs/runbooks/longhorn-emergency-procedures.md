# 🚨 Longhorn Emergency Procedures & Runbooks

Critical procedures for Longhorn storage emergencies and disaster recovery scenarios.

## 🔥 Emergency Response Matrix

| **Scenario** | **Severity** | **RTO** | **Actions** |
|--------------|--------------|---------|-------------|
| Volume Faulted | **CRITICAL** | 15 min | [Volume Faulted](#volume-faulted) |
| Backup Target Down | **HIGH** | 30 min | [Backup Target Recovery](#backup-target-recovery) |
| Node Storage Full | **HIGH** | 30 min | [Storage Full Recovery](#storage-full-recovery) |
| Multiple Node Failure | **CRITICAL** | 1 hour | [Multi-Node Recovery](#multi-node-recovery) |
| Complete Cluster Loss | **CRITICAL** | 4 hours | [Full Cluster Recovery](#full-cluster-recovery) |

---

## 🚨 CRITICAL EMERGENCIES

### Volume Faulted

**Symptoms**: Volume in "faulted" state, applications cannot access data

**IMMEDIATE ACTIONS** (within 5 minutes):

1. **Stop all applications using the faulted volume**:
   ```bash
   # Scale down deployments using the volume
   kubectl scale deployment app-name --replicas=0 -n namespace
   
   # Or delete pods using the volume
   kubectl delete pod pod-name -n namespace --force --grace-period=0
   ```

2. **Assess volume state**:
   ```bash
   kubectl get volume -n longhorn-system | grep faulted
   kubectl describe volume VOLUME_NAME -n longhorn-system
   ```

3. **Check replica status**:
   ```bash
   kubectl get replicas -n longhorn-system -l longhornvolume=VOLUME_NAME
   ```

4. **If any replica is healthy, attempt immediate backup**:
   ```bash
   ./scripts/longhorn-backup-management.sh
   # Select option 4: Create manual backup
   ```

5. **Document the incident**:
   - Volume name and size
   - Applications affected
   - Last known good backup
   - Error messages from describe output

**RECOVERY ACTIONS**:

1. **If backup successful, restore from backup**:
   ```bash
   # Create new volume from backup
   kubectl apply -f - <<EOF
   apiVersion: longhorn.io/v1beta2
   kind: Volume
   metadata:
     name: ${VOLUME_NAME}-recovered
     namespace: longhorn-system
   spec:
     fromBackup: BACKUP_NAME
     numberOfReplicas: 3
     size: "SIZE"
   EOF
   ```

2. **Update PVC to use recovered volume**:
   ```bash
   kubectl patch pvc PVC_NAME -n NAMESPACE --type='merge' \
     -p='{"spec":{"volumeName":"${VOLUME_NAME}-recovered"}}'
   ```

3. **Restart applications**:
   ```bash
   kubectl scale deployment app-name --replicas=ORIGINAL_COUNT -n namespace
   ```

### Multi-Node Recovery

**Symptoms**: Multiple Longhorn nodes offline, volumes degraded

**IMMEDIATE ACTIONS**:

1. **Assess cluster state**:
   ```bash
   kubectl get nodes
   kubectl get volumes -n longhorn-system | grep -E "(degraded|faulted)"
   ```

2. **Prioritize critical volumes**:
   ```bash
   kubectl get volumes -n longhorn-system -l data-tier=critical
   ```

3. **Emergency backup of accessible volumes**:
   ```bash
   ./scripts/longhorn-backup-management.sh
   # Select option 8: Disaster recovery backup
   ```

4. **Check remaining storage capacity**:
   ```bash
   kubectl get nodes -n longhorn-system -o custom-columns="NAME:.metadata.name,STORAGE:.status.diskStatus"
   ```

**RECOVERY ACTIONS**:

1. **Restore failed nodes** (if possible)
2. **Add new nodes** to replace failed ones
3. **Rebalance replicas** across healthy nodes
4. **Verify data integrity** after recovery

---

## 🔧 HIGH PRIORITY ISSUES

### Backup Target Recovery

**Symptoms**: Backup jobs failing, backup target unreachable

**DIAGNOSIS**:

1. **Test backup target connectivity**:
   ```bash
   # For NFS
   mount -t nfs TRUENAS_IP:/mnt/tank/longhorn-backups /tmp/test
   
   # For S3
   aws s3 ls s3://longhorn-backups --endpoint-url=https://truenas-ip:9000
   ```

2. **Check Longhorn backup target settings**:
   ```bash
   kubectl get setting backup-target -n longhorn-system -o yaml
   kubectl get setting backup-target-credential-secret -n longhorn-system -o yaml
   ```

3. **Review Longhorn manager logs**:
   ```bash
   kubectl logs -n longhorn-system -l app=longhorn-manager --tail=100
   ```

**RECOVERY ACTIONS**:

1. **Fix TrueNAS issues**:
   - Restart NFS service
   - Check dataset permissions
   - Verify network connectivity

2. **Reconfigure backup target if needed**:
   ```bash
   ./scripts/longhorn-backup-management.sh
   # Select option 1: Configure backup target
   ```

3. **Test backup functionality**:
   ```bash
   ./scripts/longhorn-backup-management.sh
   # Select option 9: Check backup system health
   ```

### Storage Full Recovery

**Symptoms**: Node storage at capacity, replica scheduling failures

**IMMEDIATE ACTIONS**:

1. **Identify storage usage**:
   ```bash
   kubectl get nodes -n longhorn-system -o custom-columns="NAME:.metadata.name,CAPACITY:.status.diskStatus.storageMaximum,AVAILABLE:.status.diskStatus.storageAvailable"
   ```

2. **Clean up unused volumes**:
   ```bash
   # List volumes not bound to PVCs
   kubectl get volumes -n longhorn-system --no-headers | while read vol state; do
     if [[ "$state" == "detached" ]]; then
       echo "Unused volume: $vol"
     fi
   done
   ```

3. **Remove old snapshots**:
   ```bash
   # List snapshots older than 7 days
   kubectl get snapshots -n longhorn-system --sort-by=.metadata.creationTimestamp
   ```

4. **Emergency cleanup**:
   ```bash
   # Delete oldest snapshots if critical
   kubectl get snapshots -n longhorn-system --sort-by=.metadata.creationTimestamp --no-headers | head -10 | awk '{print $1}' | xargs kubectl delete snapshot -n longhorn-system
   ```

**RECOVERY ACTIONS**:

1. **Add storage to nodes** (if possible)
2. **Add new nodes** with storage
3. **Rebalance replicas** to distribute load
4. **Implement storage monitoring** to prevent recurrence

---

## 🔄 FULL CLUSTER RECOVERY

### Complete Cluster Loss

**Prerequisites**:
- TrueNAS backup target accessible
- Recent backups available
- New Kubernetes cluster ready

**RECOVERY PROCEDURE**:

1. **Deploy Longhorn on new cluster**:
   ```bash
   kubectl apply -f infrastructure/storage/longhorn/
   ```

2. **Configure backup target**:
   ```bash
   kubectl patch setting backup-target -n longhorn-system --type='merge' \
     -p='{"spec":{"value":"nfs://TRUENAS_IP:/mnt/tank/longhorn-backups"}}'
   ```

3. **List available backups**:
   ```bash
   kubectl get backups -n longhorn-system
   ```

4. **Restore critical volumes first**:
   ```bash
   # Priority order: databases, user data, configurations
   ./scripts/longhorn-backup-management.sh
   # Select option 7: Restore from backup
   ```

5. **Recreate PVCs**:
   ```bash
   # For each restored volume
   kubectl apply -f - <<EOF
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: restored-pvc-name
     namespace: target-namespace
   spec:
     accessModes: [ReadWriteOnce]
     resources:
       requests:
         storage: SIZE
     storageClassName: longhorn
     volumeName: restored-volume-name
   EOF
   ```

6. **Deploy applications**:
   ```bash
   # Deploy in order: databases → core services → applications
   kubectl apply -f infrastructure/
   kubectl apply -f my-apps/
   ```

7. **Verify data integrity**:
   ```bash
   # Test each restored application
   # Verify database connections
   # Check file integrity
   ```

---

## 📋 Emergency Checklists

### Pre-Emergency Preparation

- [ ] TrueNAS backup target configured and tested
- [ ] Backup management script accessible
- [ ] Recovery procedures documented and tested
- [ ] Emergency contact information available
- [ ] Backup verification schedule in place

### During Emergency Response

- [ ] Incident logged with timestamp
- [ ] Affected systems identified
- [ ] Applications stopped if necessary
- [ ] Emergency backup created (if possible)
- [ ] Recovery plan selected and initiated
- [ ] Progress documented every 15 minutes

### Post-Emergency Verification

- [ ] All volumes restored and healthy
- [ ] Applications restarted and functional
- [ ] Data integrity verified
- [ ] Backup system restored
- [ ] Monitoring alerts cleared
- [ ] Post-incident review scheduled

---

## 🔍 Diagnostic Commands

### Quick Health Check
```bash
# Overall Longhorn health
kubectl get volumes -n longhorn-system -o custom-columns="NAME:.metadata.name,STATE:.status.state,ROBUSTNESS:.status.robustness"

# Node status
kubectl get nodes -n longhorn-system

# Recent backups
kubectl get backups -n longhorn-system --sort-by=.metadata.creationTimestamp | tail -10

# Recurring jobs
kubectl get recurringjobs -n longhorn-system
```

### Detailed Diagnostics
```bash
# Volume details
kubectl describe volume VOLUME_NAME -n longhorn-system

# Replica status
kubectl get replicas -n longhorn-system -l longhornvolume=VOLUME_NAME

# Engine status
kubectl get engines -n longhorn-system -l longhornvolume=VOLUME_NAME

# Manager logs
kubectl logs -n longhorn-system -l app=longhorn-manager --tail=50
```

### Backup System Health
```bash
# Backup target connectivity
kubectl get setting backup-target -n longhorn-system -o yaml

# Recent backup jobs
kubectl get backups -n longhorn-system -o custom-columns="NAME:.metadata.name,STATE:.status.state,PROGRESS:.status.progress,CREATED:.metadata.creationTimestamp"

# Failed backups
kubectl get backups -n longhorn-system | grep -E "(Error|Failed)"
```

---

## 📞 Escalation Procedures

### Level 1: Self-Service Recovery
- Use automated scripts
- Follow standard runbooks
- Check monitoring dashboards
- Review logs for obvious issues

### Level 2: Team Escalation
- Multiple volumes affected
- Backup system compromised
- Node failures requiring hardware intervention
- Recovery time exceeding 1 hour

### Level 3: Vendor Support
- Longhorn bugs or unexpected behavior
- Data corruption suspected
- Hardware failures affecting multiple nodes
- Recovery time exceeding 4 hours

---

## 🛡️ Prevention Measures

### Regular Testing
- Monthly backup restore tests
- Quarterly disaster recovery drills
- Annual full cluster recovery simulation

### Monitoring & Alerting
- Prometheus alerts configured
- Backup job monitoring
- Storage capacity monitoring
- Volume health monitoring

### Maintenance
- Regular Longhorn updates
- Node storage capacity planning
- Backup retention optimization
- Documentation updates

---

## 📚 Additional Resources

- [Longhorn Official Documentation](https://longhorn.io/docs/)
- [Longhorn Troubleshooting Guide](https://longhorn.io/docs/latest/troubleshooting/)
- [Backup and Restore Guide](https://longhorn.io/docs/latest/snapshots-and-backups/)
- [Performance Tuning](https://longhorn.io/docs/latest/best-practices/)

**Remember**: In emergencies, **data preservation** is the top priority. When in doubt, create backups before attempting recovery procedures. 🚨 