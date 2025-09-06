# 💾 Longhorn Backup & Recovery

**Simple backup and disaster recovery for your K3s cluster**

---

## 🚀 Quick Actions

### Backup Everything NOW
```bash
./scripts/trigger-immediate-backups.sh
```

### Check Backup Status
```bash
kubectl get backups.longhorn.io -n longhorn-system | tail -10
```

### Disaster Recovery (Fresh K3s Cluster)
```bash
# 1. Deploy Longhorn
kubectl apply -f infrastructure/storage/longhorn/

# 2. Wait for it to be ready
kubectl wait --for=condition=Available deployment/longhorn-ui -n longhorn-system --timeout=600s

# 3. Restore all data
./scripts/restore-from-backups.sh

# 4. Create volume bridges
./scripts/update-pvcs-for-restore.sh

# 5. Deploy ArgoCD
kustomize build infrastructure/controllers/argocd --enable-helm | kubectl apply -f -
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

---

## 📊 Backup Tiers

| **Tier** | **Apps** | **Frequency** | **Retention** |
|----------|----------|---------------|---------------|
| **Critical** | Paperless, Redis, Registry | Hourly snapshots + Daily backups | 30 days |
| **Important** | Khoj, Ollama, Home Assistant, Grafana | 4-hour snapshots + Daily backups | 14 days |
| **Standard** | Homepage, Cache, Logs | Daily snapshots + Weekly backups | 4 weeks |

---

## 🛠️ Common Tasks

### Single App Restore
```bash
# Scale down app
kubectl scale deployment/app-name --replicas=0 -n namespace

# Use Longhorn UI to restore volume:
# 1. Delete old volume
# 2. Restore from backup (same name!)  
# 3. Create PV/PVC (check "Use Previous PVC")

# Scale back up
kubectl scale deployment/app-name --replicas=1 -n namespace
```

### Check Backup Health
```bash
kubectl get recurringjobs.longhorn.io -n longhorn-system
kubectl get backups.longhorn.io -n longhorn-system | grep $(date +%Y-%m-%d)
```

### Access UIs
- **Longhorn**: `http://longhorn.local`
- **MinIO**: `http://192.168.10.133:9002`
- **ArgoCD**: `http://argocd.local`

---

## 🚨 Emergency Recovery Timeline

| Step | Time | Command |
|------|------|---------|
| Fresh K3s cluster | - | Your Talos deployment |
| Deploy Longhorn | 5-10 min | `kubectl apply -f infrastructure/storage/longhorn/` |
| Restore data | 15-30 min | `./scripts/restore-from-backups.sh` |
| Volume bridges | 1-2 min | `./scripts/update-pvcs-for-restore.sh` |
| Deploy apps | 3-5 min | ArgoCD bootstrap commands |

**Total: ~25-45 minutes** to full recovery

---

## ✅ Success Check

All good when these return mostly 1s (just headers):
```bash
kubectl get pods -A | grep -v Running | wc -l          # Should be 1
kubectl get pvc -A | grep -v Bound | wc -l             # Should be 1  
kubectl get applications -n argocd | grep -v Synced | wc -l  # Should be 1
```

---

**That's it!** Backups run automatically. For disasters, follow the 5-step recovery process. 🎯