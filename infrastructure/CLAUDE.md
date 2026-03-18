# Infrastructure Guidelines

> **Required reading before modifying ArgoCD configuration or sync waves:**
> - `docs/argocd.md` — Sync wave strategy, Lua health checks, server-side diff, why ApplyOutOfSyncOnly breaks ConfigMaps

## Essential Commands

### Bootstrap New Cluster

```bash
./scripts/bootstrap-argocd.sh
kubectl get applications -n argocd -w
kubectl get applications -n argocd -o custom-columns=NAME:.metadata.name,WAVE:.metadata.annotations.argocd\\.argoproj\\.io/sync-wave,STATUS:.status.sync.status
```

### ArgoCD Operations

```bash
# Check application sync status
kubectl get applications -n argocd

# Force refresh of root application (re-discovers apps)
kubectl delete application root -n argocd
kubectl apply -f infrastructure/controllers/argocd/root.yaml

# Check ApplicationSet discovery
kubectl get applicationsets -n argocd
kubectl describe applicationset infrastructure -n argocd

# Emergency reset (removes all applications)
kubectl get applications -n argocd -o name | xargs -I{} kubectl patch {} -n argocd --type json -p '[{"op": "remove","path": "/metadata/finalizers"}]'
kubectl delete applications --all -n argocd
./scripts/bootstrap-argocd.sh
```

### Talos Operations

```bash
talosctl health --nodes <node-ip>
talosctl logs -n <node-ip> -k
talosctl apply-config --nodes <node-ip> --file <config.yaml>
talosctl upgrade --nodes <node-ip> --image <installer-image>
```

### Testing & Verification

```bash
cilium status && cilium connectivity test
kubectl get externalsecret -A
kubectl get pods -n longhorn-system && kubectl get pvc -A
kubectl get nodes -l feature.node.kubernetes.io/pci-0300_10de.present=true
kubectl get gateway -A && kubectl get httproute -A
kubectl get clusterpolicy volsync-pvc-backup-restore
kubectl get replicationsource -A && kubectl get replicationdestination -A
kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber
```

## Infrastructure AppSet Rules

The Infrastructure AppSet uses an **explicit list of paths** (not glob discovery). To add a new infrastructure component:

1. Add the directory with `kustomization.yaml`
2. Add the path to `infrastructure/controllers/argocd/apps/infrastructure-appset.yaml`
3. Ensure the file is listed in `infrastructure/controllers/argocd/apps/kustomization.yaml`

**CRITICAL**: Every YAML file in `infrastructure/controllers/argocd/apps/` **must** be listed in that directory's `kustomization.yaml` under `resources:`. Unlisted files are **never deployed** — ArgoCD only sees what Kustomize renders.

```bash
# Verify after adding a new file
grep "my-new-appset.yaml" infrastructure/controllers/argocd/apps/kustomization.yaml
kubectl get applicationset -n argocd
```

Databases are auto-discovered separately by `database-appset.yaml` via `infrastructure/database/*/*` glob.

## Debugging ArgoCD

```bash
kubectl get application app-name -n argocd -o yaml
kubectl describe applicationset infrastructure -n argocd
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller

# Force manual sync
kubectl patch application app-name -n argocd --type merge -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'
```

## Debugging Secrets

```bash
kubectl get externalsecret -A
kubectl describe externalsecret app-secrets -n app-name
kubectl get pods -n 1passwordconnect
kubectl logs -n 1passwordconnect -l app.kubernetes.io/name=connect
kubectl get clustersecretstore
kubectl describe clustersecretstore 1password
```
