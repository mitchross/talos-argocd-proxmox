# Multi-Cluster Handoff Notes

## Current Direction

The branch uses a cluster-centric Kustomize layout:

```text
manifests/**/base -> clusters/talos/**
manifests/**/base -> clusters/openshift/**
```

Talos and OpenShift each run an independent upstream Helm Argo CD. Each Argo CD
scans only its own cluster folder. There is no hub/spoke model, remote cluster
registration, OpenShift GitOps Operator, or OpenShift dependency on Talos files.

## Branch

```text
feat/one-shot-multicluster-kustomize
```

## Important Decisions

- Talos remains the default and full-fidelity cluster.
- `clusters/<cluster>` contains every deployable Argo CD entrypoint.
- `manifests/**/base` contains shared sources only.
- All 44 apps have Talos and OpenShift overlays.
- Existing activation state is preserved; intentionally disabled DVWA and
  Project Nomad Kolibri resources remain disabled.
- App overlays are directory-discovered from `clusters/<cluster>/apps/*/*`.
- Explicit infrastructure, database, and monitoring entrypoints retain
  `.argocd/config.json` only where it carries real ordering, allowlist, or
  namespace intent.
- `1passwordconnect`, `cert-manager`, and `external-secrets` are shared
  portable bases under `manifests/infra`.
- Routes are complete per-cluster files.
- OpenShift GitOps owns GatewayClass `openshift-default` with controller
  `openshift.io/gateway-controller/v1`.
- Portable local PVCs use `vanillax-local-rwo`.
- Talos implements portable local storage with Longhorn.
- OpenShift implements portable local storage with LVM Storage.
- NFS and SMB CSI are shared bases consumed by both clusters.
- Talos backup/restore policy is removed from OpenShift app renders.
- OpenShift does not install Cilium, Longhorn, VolSync, or pvc-plumber.
- `targetRevision` remains `main`.
- OpenShift AppProjects remain `openshift-infrastructure` and `openshift-apps`.
- `scripts/bootstrap-cluster.sh <profile>` is the repeatable operator
  entrypoint; `scripts/bootstrap-argocd.sh <profile>` is the focused Argo-only
  step.

## Implementation Status

The branch implementation is complete through app discovery, manifest path
correction, portable infrastructure sharing, patch externalization,
profile-driven bootstrap, and OpenShift GatewayClass ownership. Full local
acceptance and final branch review remain pending. No live cluster mutation
has been performed.

## OpenShift Readiness Boundary

All apps render through OpenShift overlays, but render success is not the same
as production readiness. Before live sync, verify the OpenShift GatewayClass,
LVM schema and portable StorageClass, CSI driver SCC behavior, application SCC
behavior, external storage reachability, and backup expectations.

## Validation Commands

```bash
./scripts/validate-cluster-layout.sh
./scripts/validate-argocd-apps.sh
./scripts/validate-openshift-app-renders.sh
./scripts/validate-bootstrap-profiles.sh

find clusters -type f -name kustomization.yaml -print \
  | while read -r file; do
      kustomize build --enable-helm "$(dirname "$file")" >/dev/null
    done
```

Do not run live `kubectl apply`, `oc apply`, or Helm mutation commands during
review unless the operator explicitly requests a live bootstrap.
