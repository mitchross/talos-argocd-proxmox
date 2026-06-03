# One-Shot Multicluster Kustomize Deploy-Target Migration

## Plain-English Summary

This repo is moving from "one Talos cluster only" to "Talos by default, expandable to more clusters."

Talos remains the main reference path. A normal user can still follow the README, bootstrap one Talos cluster, and stop there. Advanced users can add optional clusters such as OpenShift, GKE, or AKS by adding a cluster bootstrap folder and Kustomize deploy targets.

Each cluster gets its own local Argo CD. Talos has one Argo CD. OpenShift has a separate Argo CD. Future GKE or AKS clusters would each have their own Argo CD too. These Argo CD instances do not manage each other, and there is no hub/spoke setup or `argocd cluster add`.

The structural change is moving apps and infrastructure into a Kustomize `base` plus `deploy-targets` model. The base describes what an app or platform component is. The deploy target describes how that thing runs on one cluster.

For example, an `echo-server` app can have one base Deployment, Service, and HTTPRoute. The Talos target patches the route to `echo.vanillax.me` and the Cilium Gateway. The OpenShift target patches the route to `echo.apps.sno-ai-lab.vanillax.xyz` and the OpenShift Gateway.

Existing Talos-only apps do not all need to become portable immediately. They can move into `deploy-targets/talos` as-is. Only apps intended to run on multiple clusters need a shared `base` plus multiple deploy targets.

Argo CD discovers deploy targets through `.argocd/config.json` files, following the reference pattern in `/home/vanillax/Downloads/devops-platform-k8s-infra-main` while avoiding collisions with app-owned `config.json` files. This is more reliable than deriving identity from nested folder names because each target explicitly declares its Application name, namespace, project, cluster, sync wave, and source path.

This is planned as one large structural branch because the Talos cluster may be nuked and rebuilt. That lets the repo optimize for the clean long-term layout instead of preserving old live Argo CD Application names.

## Branch Implementation Notes

Implemented on branch:

```text
feat/one-shot-multicluster-kustomize
```

Material implementation choices:

- Metadata files live at `.argocd/config.json` under each deploy target, not at deploy-target root, because some applications already have app-owned `config.json` files.
- Metadata includes explicit `sourcePath`; AppSets do not infer source paths from `.path.path`.
- Database resources moved under `manifests/database/.../deploy-targets/talos`.
- All existing applications are migrated one-shot into `manifests/apps/**/deploy-targets/talos`.
- OpenShift deploys every app that has `deploy-targets/openshift/.argocd/config.json`.
- `manifests/apps/media/echo-server` is the current cross-cluster smoke test, with `base/`, `deploy-targets/talos/`, and `deploy-targets/openshift/`.
- OpenShift starts with upstream Helm Argo CD, 1Password Connect, External Secrets, cert-manager, LVM storage starter manifests, Gateway API, and the OpenShift app AppSet.
- OpenShift storage strategy is documented in `docs/domains/multicluster/openshift-storage-and-app-migration.md`: local LVM for small PVCs, NFS for AI/shared large data, and defer large stateful apps until storage/SCC/backup decisions are explicit.
- OpenShift live schema assumptions remain flagged for GatewayClass and LVM Storage Operator resources.

## Goal

Refactor `talos-argocd-proxmox` into a clean, long-term multicluster GitOps reference while keeping Talos as the default single-cluster path.

The repo should support:

- One default Talos cluster for normal homelab users.
- Optional expansion clusters such as OpenShift, GKE, AKS, or similar.
- One local Argo CD instance per cluster.
- Kustomize base/deploy-target overlays for platform-specific differences.
- No hub/spoke Argo registration.
- No `argocd cluster add`.

This is a one-shot structural migration branch. Talos may be nuked/rebuilt, so live Argo Application adoption compatibility is not the primary design constraint.

## Architecture

Each cluster owns its own upstream Helm-installed Argo CD:

```text
Talos      -> local Argo CD -> clusters/talos/argocd
OpenShift  -> local Argo CD -> clusters/openshift/argocd
Future GKE -> local Argo CD -> clusters/gke/argocd
```

Each Argo CD manages only:

```text
https://kubernetes.default.svc
```

No cluster manages another cluster.

## Target Folder Tree

```text
clusters/
  talos/
    bootstrap/
      README.md
      kustomization.yaml
      ns.yaml
      root.yaml
      values.yaml
    argocd/
      kustomization.yaml
      projects.yaml
      bootstrap/
      core-dependencies/
      custom-entrypoints/
      appsets/

  openshift/
    bootstrap/
      README.md
      kustomization.yaml
      ns.yaml
      root.yaml
      values.yaml
    argocd/
      kustomization.yaml
      projects.yaml
      bootstrap/
      core-dependencies/
      appsets/

manifests/
  infra/
    argocd/
      base/
      deploy-targets/
        talos/
        openshift/
    cilium/
      deploy-targets/talos/
    gateway/
      base/
      deploy-targets/
        talos/
        openshift/
    cert-manager/
      base/
      deploy-targets/
        talos/
        openshift/
    external-secrets/
      base/
      deploy-targets/
        talos/
        openshift/
    1passwordconnect/
      base/
      deploy-targets/
        talos/
        openshift/
    longhorn/
      deploy-targets/talos/
    volsync/
      deploy-targets/talos/
    pvc-plumber/
      deploy-targets/talos/
    lvm-storage/
      deploy-targets/openshift/

  monitoring/
    prometheus-stack/
      deploy-targets/talos/
    loki-stack/
      deploy-targets/talos/
    tempo/
      deploy-targets/talos/

  apps/
    <category>/<app>/
      base/
      deploy-targets/
        talos/
        openshift/

components/
  talos/
    kustomization.yaml
  openshift/
    kustomization.yaml
```

Existing Talos-only apps do not need a shared `base` immediately. They can move mechanically into:

```text
manifests/apps/<category>/<app>/deploy-targets/talos/
```

Only portable apps need:

```text
base/
deploy-targets/talos/
deploy-targets/openshift/
```

## Bootstrap Model

Every cluster follows the same bootstrap contract:

1. Get kube access.
2. Satisfy cluster-specific prerequisites.
3. Pre-seed 1Password secrets.
4. Helm install upstream Argo CD with cluster-specific values.
5. Apply that cluster's root Application.
6. Argo CD manages the cluster from Git.

Future command shape:

```bash
./scripts/bootstrap-argocd.sh talos
./scripts/bootstrap-argocd.sh openshift
```

Talos bootstrap includes:

```text
Omni kubeconfig
Cilium first install
Gateway API CRDs
1Password pre-seed
Argo CD Helm install
clusters/talos/bootstrap/root.yaml
```

OpenShift bootstrap includes:

```text
oc/kubeconfig access
verify OpenShift platform prerequisites
1Password pre-seed
Argo CD Helm install with OpenShift values
clusters/openshift/bootstrap/root.yaml
```

OpenShift must not install Cilium or Longhorn.

## Argo CD AppSets

Use `.argocd/config.json` file generators, not `path.basename`.

Example deploy-target metadata:

```json
{
  "applicationName": "openshift-apps-media-echo-server",
  "cluster": "openshift",
  "project": "openshift-apps",
  "namespace": "echo-server",
  "part": "apps",
  "syncWave": "6",
  "sourcePath": "manifests/apps/media/echo-server/deploy-targets/openshift"
}
```

Example AppSet:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: openshift-apps
  namespace: argocd
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - git:
        repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
        revision: main
        files:
          - path: manifests/apps/*/*/deploy-targets/openshift/.argocd/config.json
  template:
    metadata:
      name: "{{.applicationName}}"
      annotations:
        argocd.argoproj.io/manifest-generate-paths: "{{.sourcePath}}"
        argocd.argoproj.io/sync-wave: "{{.syncWave}}"
    spec:
      project: "{{.project}}"
      source:
        repoURL: https://github.com/mitchross/talos-argocd-proxmox.git
        targetRevision: main
        path: "{{.sourcePath}}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{.namespace}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
          allowEmpty: false
        syncOptions:
          - CreateNamespace=true
          - ServerSideApply=true
          - RespectIgnoreDifferences=true
          - Replace=false
```

## Naming

Because Talos may be rebuilt, use clean long-term names:

```text
talos-infra-cilium
talos-infra-gateway
talos-infra-external-secrets
talos-monitoring-prometheus-stack
talos-apps-jellyfin

openshift-infra-gateway
openshift-infra-external-secrets
openshift-infra-lvm-storage
openshift-apps-media-echo-server
```

Cross-cluster name collision is not a concern because each cluster has its own Argo CD.

## Cluster Differences

Talos deploy targets carry:

```text
Cilium
Cilium Gateway API parentRefs
*.vanillax.me domains
Longhorn
VolSync
pvc-plumber
current monitoring stack
current app catalog
```

OpenShift deploy targets carry:

```text
OpenShift Gateway API
*.apps.sno-ai-lab.vanillax.xyz domains
OpenShift Gateway parentRefs
LVM storage
SCC/securityContext patches
OpenShift namespaces
OpenShift-only infra
any app with an OpenShift deploy target
```

## Portable App Example

Base:

```text
manifests/apps/media/echo-server/base/
  deployment.yaml
  service.yaml
  httproute.yaml
  kustomization.yaml
```

Base `HTTPRoute` uses placeholders:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: echo-server
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: placeholder
      namespace: placeholder
      sectionName: https
  hostnames:
    - placeholder.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - group: ""
          kind: Service
          name: echo-server
          port: 80
          weight: 1
```

Talos overlay patches:

```yaml
resources:
  - ../../base

patches:
  - target:
      kind: HTTPRoute
      name: echo-server
    patch: |-
      - op: replace
        path: /spec/parentRefs/0/name
        value: gateway-internal
      - op: replace
        path: /spec/parentRefs/0/namespace
        value: gateway
      - op: replace
        path: /spec/hostnames/0
        value: echo.vanillax.me
```

OpenShift overlay patches:

```yaml
resources:
  - ../../base

components:
  - ../../../../components/openshift

patches:
  - target:
      kind: HTTPRoute
      name: echo-server
    patch: |-
      - op: replace
        path: /spec/parentRefs/0/name
        value: openshift-gateway
      - op: replace
        path: /spec/parentRefs/0/namespace
        value: openshift-ingress
      - op: replace
        path: /spec/hostnames/0
        value: echo.apps.sno-ai-lab.vanillax.xyz
```

## Migration Order

1. Create a branch.
2. Create `clusters/`, `manifests/`, and `components/` skeletons.
3. Move Argo CD bootstrap into `clusters/talos/bootstrap`.
4. Add `clusters/openshift/bootstrap`.
5. Move Talos Argo app tree into `clusters/talos/argocd`.
6. Add `clusters/openshift/argocd`.
7. Convert AppSets to `.argocd/config.json` file generators.
8. Move Talos infrastructure into `manifests/infra/*/deploy-targets/talos`.
9. Move Talos monitoring into `manifests/monitoring/*/deploy-targets/talos`.
10. Move Talos apps into `manifests/apps/*/*/deploy-targets/talos`.
11. Add OpenShift deploy targets for 1Password Connect, External Secrets, cert-manager, Gateway API/Gateway, LVM storage, and one trivial stateless app.
12. Update bootstrap script to accept a cluster argument.
13. Update README so Talos remains the default single-cluster path.
14. Validate all Kustomize renders.
15. Review before any live apply.

## Validation

Local only:

```bash
kustomize build --enable-helm clusters/talos/bootstrap
kustomize build --enable-helm clusters/openshift/bootstrap
kustomize build clusters/talos/argocd
kustomize build clusters/openshift/argocd
```

Render all deploy targets:

```bash
find manifests -path '*/deploy-targets/*/kustomization.yaml' -print \
  | while read -r file; do
      kustomize build --enable-helm "$(dirname "$file")" >/dev/null
    done
```

Check metadata:

```bash
rg -n '"applicationName"|"cluster"|"project"|"namespace"|"syncWave"|"sourcePath"' manifests
rg -n 'targetRevision: (HEAD|master)' clusters manifests
```

Cluster checks only when intentionally pointed at the right context:

```bash
kubectl config current-context
kubectl get crd applications.argoproj.io applicationsets.argoproj.io
kubectl get gatewayclass,gateway,httproute -A
```

## Explicit Non-Goals

Do not use OpenShift GitOps Operator as the foundation for this migration.

Do not use hub/spoke Argo.

Do not register remote clusters into another Argo CD.

Do not make OpenShift install Cilium or Longhorn.

Do not require every existing Talos app to be made portable immediately.

## Acceptance Criteria

- Talos remains the clear default cluster in README.
- OpenShift is additive and optional.
- Both clusters have independent local Argo CD bootstrap paths.
- Argo app trees render locally.
- Every deploy target renders locally.
- Existing Talos apps are represented under `manifests/apps/.../deploy-targets/talos`.
- OpenShift has infra deploy targets and an apps AppSet that picks up any OpenShift app deploy target.
- AppSets discover deploy targets via `.argocd/config.json`.
- No live cluster mutation is required to review the branch.
