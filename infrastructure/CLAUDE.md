# Infrastructure Guidelines

> **Required reading before modifying ArgoCD configuration or sync waves:**
> - `docs/domains/argocd/argocd.md` — Sync wave strategy, Lua health checks, server-side diff, why ApplyOutOfSyncOnly breaks ConfigMaps

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

# Refresh the root comparison without deleting the Application
kubectl -n argocd annotate application root argocd.argoproj.io/refresh=hard --overwrite
kubectl -n argocd get application root

# Check ApplicationSet discovery
kubectl get applicationsets -n argocd
kubectl describe applicationset infrastructure -n argocd
```

A refresh requests a new comparison; it does not sync changes or rebuild the
cluster. Check the Application status and conditions afterward. If reconciliation
fails, inspect the error before taking further action. For an intentional rebuild,
follow [the disaster-recovery runbook](../docs/disaster-recovery.md) and its
preflight checks instead of deleting Applications as a troubleshooting shortcut.

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
# kopiur backup CRs across all namespaces (Snapshot should reach Succeeded):
kubectl get snapshotpolicy,snapshotschedule,restore,snapshot -A
kubectl get pods -n kopiur-system
kubectl logs -n kopiur-system -l app.kubernetes.io/name=kopiur --tail=50
```

## Infrastructure AppSet Rules

The Infrastructure AppSet uses an **explicit list of paths** (not glob discovery). To add a new infrastructure component:

1. Add the directory with `kustomization.yaml`
2. Add the path to `infrastructure/controllers/argocd/apps/appsets/infrastructure-appset.yaml`
3. Add any new explicit Application/ApplicationSet entrypoint to
   `infrastructure/controllers/argocd/apps/kustomization.yaml`. Editing an existing
   AppSet path list does not require another entrypoint.

**CRITICAL**: Every YAML file in `infrastructure/controllers/argocd/apps/` **must** be listed in that directory's `kustomization.yaml` under `resources:`. Unlisted files are **never deployed** — ArgoCD only sees what Kustomize renders.

```bash
# Verify after adding a new file
grep "my-new-appset.yaml" infrastructure/controllers/argocd/apps/kustomization.yaml
kubectl get applicationset -n argocd
```

Databases are discovered separately by `database-appset.yaml` via the
`infrastructure/database/*/*` glob (Redis + shared DB support — fully
automated). Actual databases are plain Postgres Deployments inside their
owning app's directory and restore via kopiur like any other PVC; a
fresh-cluster restore needs no database-specific steps (CNPG and its
recovery script were retired 2026-08-13).

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
