# OpenShift Argo CD Bootstrap

This directory contains the hand-run upstream Helm Argo CD bootstrap inputs for
the OpenShift cluster.

This repo does not use the OpenShift GitOps Operator for OpenShift bootstrap.
It uses the same shape as Talos:

```text
helm install upstream Argo CD -> apply root Application -> local Argo CD self-manages
```

Use the repo-level script from the repository root:

```bash
./scripts/bootstrap-argocd.sh openshift
```

Before running it, verify:

- `kubectl` or `oc` points at the intended OpenShift cluster.
- 1Password Connect and External Secrets token secrets are pre-seeded.
- Gateway API is available.
- The OpenShift GatewayClass name matches `clusters/openshift/infra/gateway/gateway.yaml`.
- The LVM Storage Operator channel and `LVMCluster` schema match the live cluster.

Manual equivalent:

```bash
kubectl apply -f clusters/openshift/bootstrap/ns.yaml
helm upgrade --install argocd argo-cd \
  --repo https://argoproj.github.io/argo-helm \
  --version 9.5.17 \
  --namespace argocd \
  --values clusters/openshift/bootstrap/values.yaml \
  --wait \
  --timeout 10m
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s
kubectl apply -f clusters/openshift/bootstrap/root.yaml
```

`kustomization.yaml` renders the Helm bootstrap locally for validation. The root
Application is applied separately after the Application CRD exists.
