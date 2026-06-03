# Talos Argo CD Bootstrap

This directory contains the hand-run upstream Helm Argo CD bootstrap inputs for
the Talos cluster.

Use the repo-level script from the repository root:

```bash
./scripts/bootstrap-argocd.sh talos
```

The script expects Talos prerequisites to be complete first:

- Omni service-account kubeconfig points at the Talos cluster.
- Cilium is installed at the version pinned for the Talos deploy target.
- Gateway API CRDs are installed.
- 1Password Connect and External Secrets token secrets are pre-seeded.

Manual equivalent:

```bash
kubectl apply -f clusters/talos/bootstrap/ns.yaml
helm upgrade --install argocd argo-cd \
  --repo https://argoproj.github.io/argo-helm \
  --version 9.5.17 \
  --namespace argocd \
  --values clusters/talos/bootstrap/values.yaml \
  --wait \
  --timeout 10m
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s
kubectl apply -f clusters/talos/bootstrap/root.yaml
```

`kustomization.yaml` renders the Helm bootstrap locally for validation. The root
Application is applied separately after the Application CRD exists.
