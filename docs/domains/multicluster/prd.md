# PRD: One-Shot Multicluster Kustomize Deploy-Target GitOps

## Plain-English Summary

This repo is Talos-first and multicluster-ready.

A normal user can bootstrap one Talos cluster and stop there. Advanced users can
add optional clusters such as OpenShift, GKE, or AKS by adding a cluster
bootstrap tree plus Kustomize deploy targets.

Each cluster runs its own local upstream Helm Argo CD. Talos has one Argo CD.
OpenShift has another Argo CD. Future clusters get their own Argo CD too. These
instances do not manage each other. There is no hub/spoke model and no
`argocd cluster add`.

The repo uses `base/` plus `deploy-targets/<cluster>/` where portability matters.
Existing Talos-only apps can stay as mechanical Talos deploy targets. Only apps
that run on multiple clusters need a shared base.

## Goals

- Keep Talos the default single-cluster reference path.
- Add OpenShift as an optional expansion cluster.
- Use one local upstream Helm Argo CD per cluster.
- Keep all Argo state in Git.
- Use Kustomize overlays/deploy targets for platform differences.
- Discover deploy targets through explicit metadata, not path basename guessing.
- Avoid OpenShift GitOps Operator for this repo's bootstrap model.

## Non-Goals

- No hub/spoke Argo CD.
- No remote-cluster registration.
- No OpenShift GitOps Operator foundation.
- No OpenShift Cilium or Longhorn install.
- No requirement to make every Talos app portable immediately.
- No cross-cluster failover or global traffic routing in this branch.

## Architecture

```text
Talos      -> local upstream Helm Argo CD -> clusters/talos/argocd
OpenShift  -> local upstream Helm Argo CD -> clusters/openshift/argocd
Future GKE -> local upstream Helm Argo CD -> clusters/gke/argocd
```

Each Argo CD manages only:

```text
https://kubernetes.default.svc
```

## Repository Shape

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
    <component>/deploy-targets/<cluster>/
  database/
    <engine>/<instance>/deploy-targets/talos/
  monitoring/
    <component>/deploy-targets/talos/
  apps/
    <category>/<app>/
      base/
      deploy-targets/
        talos/
        openshift/

components/
  talos/
  openshift/
```

## Bootstrap Contract

Every cluster follows the same shape:

1. Get kube access.
2. Satisfy cluster-specific prerequisites.
3. Pre-seed 1Password secrets.
4. Helm install upstream Argo CD with cluster-specific values.
5. Apply that cluster's root Application.
6. Let that cluster's local Argo CD manage the cluster from Git.

Commands:

```bash
./scripts/bootstrap-argocd.sh talos
./scripts/bootstrap-argocd.sh openshift
```

Talos prerequisites:

- Omni service-account kubeconfig.
- Cilium installed first.
- Gateway API CRDs installed.
- 1Password secrets pre-seeded.

OpenShift prerequisites:

- `kubectl` or `oc` access to the cluster.
- Gateway API available.
- OLM available for the starter LVM Storage Operator subscription.
- 1Password secrets pre-seeded.

## ApplicationSet Metadata

AppSets use Git `files` generators over:

```text
*/deploy-targets/<cluster>/.argocd/config.json
```

The metadata is stored under `.argocd/` to avoid collisions with application
files named `config.json`, such as workload config seeds.

Example:

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

AppSet template shape:

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
```

## Cluster Differences

Talos deploy targets own:

- Cilium.
- Cilium Gateway API parentRefs.
- `*.vanillax.me` hostnames.
- Longhorn.
- VolSync and pvc-plumber.
- Monitoring.
- The full current app catalog.

OpenShift deploy targets own:

- OpenShift Gateway API manifests.
- `*.apps.sno-ai-lab.vanillax.xyz` hostnames.
- OpenShift Gateway parentRefs.
- The full current app catalog as first-pass OpenShift deploy targets.
- `longhorn` PVCs patched to the assumed local LVM StorageClass `lvms-vg1`.
- Existing NFS/SMB/static storage references left explicit until an OpenShift NFS/SMB implementation is chosen.
- OpenShift-specific Gateway and fixed UID/GID securityContext patches where generated.

## Application Migration Model

All existing applications are migrated in one shot to:

```text
manifests/apps/<category>/<app>/deploy-targets/talos/
```

That is the migration scope. An app does not need to become cross-cluster on the
same day to participate in the new layout.

OpenShift app deployment is also one-shot from Argo CD's point of view: the
OpenShift AppSet scans all OpenShift deploy-target metadata. Every existing app
now has this file and is included automatically:

```text
manifests/apps/<category>/<app>/deploy-targets/openshift/.argocd/config.json
```

All apps are present for OpenShift catalog-level testing. Production readiness is
still per app: use local LVM for small PVCs, choose NFS/SMB/static PV handling
for large shared data, and review SCC/securityContext plus backup behavior before
trusting large stateful apps. See
`docs/domains/multicluster/openshift-storage-and-app-migration.md`.

Most OpenShift app targets are generated overlays over their Talos sibling:

```text
manifests/apps/<category>/<app>/deploy-targets/openshift/
```

`manifests/apps/media/echo-server` remains the clean portable example with a
shared `base/`; the rest are first-pass overlays so the whole catalog is visible
to OpenShift Argo CD.

## Schema Assumptions To Verify Live

These render locally but require live OpenShift verification before sync:

- GatewayClass name is assumed to be `openshift-default`.
- LVM Storage Operator Subscription uses `channel: stable-4.20`.
- `LVMCluster` uses `apiVersion: lvm.topolvm.io/v1alpha1`.
- OpenShift Gateway controller behavior for cert-manager Gateway shim must be verified.
- `lvms-vg1` is assumed to be the OpenShift local LVM StorageClass for PVCs migrated from `longhorn`.
- Existing Talos NFS/SMB/static storage references need OpenShift storage implementation before affected apps become healthy.
- Upstream Helm chart `openshift.enabled: true` is used for Argo CD; no `ArgoCD` CR or `spec.extraConfig` exists in this design because the OpenShift GitOps Operator path was rejected.

## Validation

Local:

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

Live checks only when pointed at the intended context:

```bash
kubectl config current-context
kubectl get gatewayclass,gateway,httproute -A
kubectl get crd applications.argoproj.io applicationsets.argoproj.io
```
