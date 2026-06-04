# Talos Argo CD Bootstrap

This directory contains the hand-run upstream Helm Argo CD bootstrap inputs for
the Talos cluster.

Use the repo-level script from the repository root:

```bash
./scripts/bootstrap-cluster.sh talos
```

The profile wrapper:

- Omni service-account kubeconfig points at the Talos cluster.
- installs or verifies Cilium at the version pinned in
  `clusters/talos/infra/cilium`;
- installs pinned upstream Gateway API CRDs;
- verifies the three pre-seeded 1Password secrets;
- calls `scripts/bootstrap-argocd.sh talos` after prerequisites pass.

On a fresh Talos cluster, the first invocation may complete networking and then
stop at the secret gate. Pre-seed the secrets and rerun the same command.

Direct `scripts/bootstrap-argocd.sh talos` invocation is the focused Argo-only
step and assumes every platform prerequisite is already complete.

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
