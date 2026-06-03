# Multi-Cluster Handoff Notes

## Current Direction

The current branch implements the one-shot multicluster Kustomize deploy-target
migration.

The old OpenShift GitOps Operator plan is superseded. The repo now follows the
same bootstrap style on Talos and OpenShift:

```text
hand-run upstream Helm Argo CD -> apply cluster root Application -> local Argo CD self-manages
```

There is one Argo CD per cluster. There is no hub/spoke setup and no
`argocd cluster add`.

## Branch

Work is on:

```text
feat/one-shot-multicluster-kustomize
```

## Key Files

- `README.md` - top-level Talos-first and OpenShift-optional bootstrap guide.
- `docs/domains/multicluster/prd.md` - current PRD.
- `docs/plans/2026-06-03-one-shot-multicluster-kustomize-migration.md` - planning note for the one-shot migration.
- `docs/domains/multicluster/openshift-storage-and-app-migration.md` - OpenShift storage and app eligibility notes.
- `clusters/talos/bootstrap/` - Talos hand-run Argo CD bootstrap inputs.
- `clusters/talos/argocd/` - Talos app-of-apps tree.
- `clusters/openshift/bootstrap/` - OpenShift hand-run Argo CD bootstrap inputs.
- `clusters/openshift/argocd/` - OpenShift app-of-apps tree.
- `manifests/**/deploy-targets/<cluster>/.argocd/config.json` - AppSet metadata.

## Important Decisions

- Talos remains the default/reference cluster.
- OpenShift is additive and optional.
- OpenShift does not install Cilium or Longhorn.
- OpenShift uses upstream Helm Argo CD, not the OpenShift GitOps Operator.
- AppSets use `.argocd/config.json` files rather than `path.basename`.
- The metadata file lives under `.argocd/` to avoid colliding with app-owned `config.json` files.
- `targetRevision` is `main`.
- OpenShift AppProjects are `openshift-infrastructure` and `openshift-apps`.
- All current applications are migrated one-shot into `manifests/apps/**/deploy-targets/talos`.
- OpenShift deploys every app that has `deploy-targets/openshift/.argocd/config.json`.
- `echo-server` is the current cross-cluster smoke test, not the limit of the migration.
- Large stateful apps should not get OpenShift deploy targets until each has an explicit storage plan.
- Use OpenShift local LVM for small PVCs and NFS for AI/shared/large-but-portable data.

## Live Schema Assumptions Still Needing Verification

These render locally but must be confirmed before syncing OpenShift:

- GatewayClass name: currently assumed `openshift-default`.
- LVM Storage Operator channel: currently `stable-4.20`.
- `LVMCluster` API: currently `lvm.topolvm.io/v1alpha1`.
- cert-manager Gateway shim behavior for the OpenShift Gateway.
- SCC compatibility for copied upstream Helm charts such as 1Password Connect, External Secrets, and cert-manager.

## Validation Commands

```bash
./scripts/validate-argocd-apps.sh
kustomize build --enable-helm clusters/talos/bootstrap
kustomize build --enable-helm clusters/openshift/bootstrap
kustomize build clusters/talos/argocd
kustomize build clusters/openshift/argocd
```

Render every deploy target:

```bash
find manifests -path '*/deploy-targets/*/kustomization.yaml' -print \
  | while read -r file; do
      kustomize build --enable-helm "$(dirname "$file")" >/dev/null
    done
```

Do not run live `kubectl apply`, `oc apply`, or Helm mutation commands during
review unless the operator explicitly asks for a live bootstrap.
