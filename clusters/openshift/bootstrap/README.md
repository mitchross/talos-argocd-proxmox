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
./scripts/bootstrap-cluster.sh openshift
```

The profile wrapper:

- `kubectl` or `oc` points at the intended OpenShift cluster.
- verifies OpenShift-managed Gateway API CRDs;
- rejects a conflicting Service Mesh Operator v2 subscription;
- never installs Cilium or upstream Gateway API CRDs;
- verifies the three pre-seeded 1Password secrets;
- calls `scripts/bootstrap-argocd.sh openshift` after prerequisites pass.

Git owns GatewayClass `openshift-default` with controller
`openshift.io/gateway-controller/v1`. The LVM Storage Operator channel and
`LVMCluster` schema still require live verification.

Direct `scripts/bootstrap-argocd.sh openshift` invocation is the focused
Argo-only step and assumes every platform prerequisite is already complete.

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
