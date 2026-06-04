# Multi-Cluster Handoff Notes

> **Canonical continuation note:** Read this file before any multicluster,
> OpenShift, Gateway API, LVM Storage, route-domain, or bootstrap work. The
> structural migration is locally accepted, but the live OpenShift target is
> **not ready for bootstrap** as of June 4, 2026.

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

The original repository feature branch uses `targetRevision: main` with Argo CD
URLs pointing at the original repository. Do not bootstrap OpenShift from that
branch checkout: Argo CD would reconcile the original repository's `main`, not
the feature branch.

An isolated public test repository exists specifically for live OpenShift
testing:

```text
https://github.com/mitchross/talos-argocd-proxmox-multicluster-test
branch: main
source feature commit: 1a7f36f1
```

Its test-only commit `4410b906` rewrites Argo CD repository URLs to the
isolated test repository. Its test-only commit `f5239d95` adds manual GitHub
Actions dispatch. Cluster CI passed in that repository:

```text
https://github.com/mitchross/talos-argocd-proxmox-multicluster-test/actions/runs/26975463740
```

Talos can remain on the original repository and current main branch while the
isolated test repository is used against OpenShift. The two local Argo CD
instances are independent.

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

The branch implementation and local acceptance completed on June 4, 2026. It
includes app discovery, manifest path correction, portable infrastructure
sharing, patch externalization, profile-driven bootstrap, OpenShift
GatewayClass ownership, and final bootstrap profile isolation. No live cluster
mutation was performed.

Implementation commits:

- `0313c64b` directory-derived app discovery
- `5b4bbca2` corrected manifest-generation paths
- `1d23d748` shared portable infrastructure bases
- `b939f7eb` externalized Kustomize patches
- `872326f2` profile-driven bootstrap and OpenShift GatewayClass
- `96bd15c3` shared-manifest patch-style guardrail
- `49c34706` operator documentation
- `0d3d2c61` bootstrap profile isolation and stronger preflight

## Local Acceptance

- 88/88 app renders are byte-identical to the pre-migration baseline.
- The 88-row generated Application contract is unchanged.
- All repository-local validators and shellcheck pass.
- All 155 cluster kustomizations render successfully.
- OpenShift bootstrap dry-run succeeds without any Talos cluster files.
- No app metadata, escaped or multiline inline patches, deprecated patch
  fields, invalid manifest-generation paths, or `targetRevision: HEAD` values
  remain.
- The render pass emits 27 existing `commonLabels` deprecation warnings; that
  cleanup is separate from this migration.

## OpenShift Readiness Boundary

All apps render through OpenShift overlays, but render success is not the same
as production readiness. Before live sync, verify the OpenShift GatewayClass,
LVM schema and portable StorageClass, CSI driver SCC behavior, application SCC
behavior, external storage reachability, and backup expectations.

## Verified Live OpenShift State

All checks below were read-only and used the explicit kubeconfig:

```text
/home/vanillax/Downloads/sno-ai-lab-kubeconfig
context: admin
API: https://api.sno-ai-lab.vanillax.xyz:6443
```

No `kubectl apply`, `oc apply`, Helm mutation, namespace creation, secret
creation, or other live mutation was performed.

Verified cluster facts:

- OpenShift `4.22.0-rc.5`, channel `stable-4.22`; Kubernetes `v1.35.5`.
- Single-node cluster `sno-ai-lab.lan`, node IP `192.168.10.10`.
- Platform `None`, control plane and infrastructure topology `SingleReplica`.
- OVN-Kubernetes; pod network `10.128.0.0/14`; service network
  `172.30.0.0/16`.
- Base domain `sno-ai-lab.vanillax.xyz`.
- Default OpenShift ingress domain `apps.sno-ai-lab.vanillax.xyz`.
- Default IngressController is healthy and uses `HostNetwork` on
  `192.168.10.10`.
- Gateway API CRDs `v1`/`v1beta1`, bundle `v1.4.1`, are installed.
- No `GatewayClass`, `Gateway`, or `HTTPRoute` exists yet.
- No active OSSM v2 subscription was found.
- No `argocd` namespace or Argo CD CRDs exist.
- Required pre-seeded 1Password namespaces/secrets do not exist.

The OpenShift GatewayClass contract remains plausible: official OKD 4.20 and
OpenShift 4.21 documentation require
`controllerName: openshift.io/gateway-controller/v1`. Creating that
GatewayClass causes the Ingress Operator to install the Gateway API service
mesh implementation. This behavior is still unverified on the live
`4.22.0-rc.5` cluster.

Primary references:

- [OKD 4.20 Gateway API with networking](https://docs.okd.io/4.20/networking/ingress_load_balancing/configuring_ingress_cluster_traffic/ingress-gateway-api.html)
- [OpenShift 4.20 persistent storage using LVM Storage](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/storage/persistent-storage-using-local-storage)

## Current Live Bootstrap Blockers

Do **not** run `./scripts/bootstrap-cluster.sh openshift` yet. The script
checks Gateway CRDs, OSSM v2, and secrets, but it does not currently catch all
of these live blockers before installing Argo CD.

### 1. LVM Storage Is Unavailable

- Live `Subscription/openshift-storage/lvms-operator` is
  `ResolutionFailed`.
- Failure message: no operators found in package `lvms-operator` in the
  referenced `redhat-operators` catalog.
- There is no installed LVM CSV, no `LVMCluster` CRD, no TopoLVM API, no LVM
  pods, and no StorageClass.
- Repo manifest pins channel `stable-4.20`; the live cluster is
  `4.22.0-rc.5` on `stable-4.22`.
- Repo uses namespace `openshift-storage`; current Red Hat 4.20 documentation
  describes `openshift-lvm-storage` as the default namespace. Confirm the
  supported 4.22 operator/package/channel/namespace before changing Git.

Until this is resolved, every OpenShift app PVC using
`vanillax-local-rwo` will remain Pending.

### 2. Gateway LoadBalancer Publishing Is Unavailable

- The OpenShift Gateway implementation provisions a `LoadBalancer` Service for
  each Gateway.
- The live bare-metal/platform-None cluster has no LoadBalancer Services,
  MetalLB APIs, MetalLB subscription, or other observed load-balancer provider.
- `192.168.10.230` is not currently reachable from the operator workstation;
  ARP resolution reports `FAILED`.

Before Gateway sync, select and verify the bare-metal LoadBalancer/IP
advertisement mechanism and reserve the intended Gateway address.

### 3. Route Domain And DNS Currently Collide With Default OpenShift Ingress

Cloudflare currently contains:

```text
*.apps.sno-ai-lab.vanillax.xyz         -> 192.168.10.10
*.gateway.apps.sno-ai-lab.vanillax.xyz -> 192.168.10.230
```

Authoritative and local DNS tests both resolve
`test.gateway.apps.sno-ai-lab.vanillax.xyz` to `192.168.10.10`, not `.230`.
The broader `*.apps...` record currently captures the nested name.

The repo also currently configures the OpenShift Gateway listener and all app
HTTPRoutes under `*.apps.sno-ai-lab.vanillax.xyz`. Those names therefore point
at the default OpenShift HostNetwork router on `.10`, not the future Gateway
API LoadBalancer.

Recommended direction:

- Preserve `*.apps.sno-ai-lab.vanillax.xyz -> 192.168.10.10` for OpenShift
  console, OAuth, and ordinary Route traffic.
- Give GitOps-managed Gateway API apps a distinct subdomain such as
  `*.gateway.apps.sno-ai-lab.vanillax.xyz`.
- Update the Gateway listener, Argo CD URLs, and app HTTPRoutes together.
- Fix authoritative DNS behavior and verify the chosen Gateway IP before
  bootstrap.

Do not move the existing default `*.apps...` wildcard away from `.10`; doing so
would disrupt built-in OpenShift routes.

### 4. Bootstrap Secrets Are Not Pre-Seeded

The live cluster has none of:

```text
1passwordconnect/1password-credentials
1passwordconnect/1password-operator-token
external-secrets/1passwordconnect
```

This is expected on the fresh cluster. Pre-seed them only after the storage,
Gateway publishing, and route-domain decisions above are resolved.

## Safe Next Actions

1. Resolve LVM Storage for OpenShift `4.22.0-rc.5` and prove that
   `vanillax-local-rwo` can bind a test PVC.
2. Choose and install/configure a bare-metal LoadBalancer implementation for
   Gateway API, then prove the chosen external IP is reachable.
3. Change the OpenShift Gateway/API app domain to the dedicated subdomain and
   verify authoritative DNS resolution.
4. Re-run read-only preflight checks.
5. Pre-seed the three 1Password secrets.
6. Clone the isolated test repository and run
   `./scripts/bootstrap-cluster.sh openshift` with
   `KUBECONFIG=/home/vanillax/Downloads/sno-ai-lab-kubeconfig`.

Do not mutate Talos during OpenShift testing.

## Read-Only Live Recheck

Use the explicit OpenShift kubeconfig for every command:

```bash
export KUBECONFIG=/home/vanillax/Downloads/sno-ai-lab-kubeconfig

kubectl get clusterversion version
kubectl get node -o wide
kubectl get clusteroperator ingress network -o wide
kubectl get gatewayclass,gateway,httproute -A
kubectl get subscriptions.operators.coreos.com -A
kubectl get subscription lvms-operator -n openshift-storage -o yaml
kubectl get crd | grep -Ei 'gateway|lvm|topolvm'
kubectl get storageclass
kubectl get svc -A -o wide | grep LoadBalancer
kubectl get secret -n 1passwordconnect 1password-credentials
kubectl get secret -n 1passwordconnect 1password-operator-token
kubectl get secret -n external-secrets 1passwordconnect

dig @1.1.1.1 +short A argocd.apps.sno-ai-lab.vanillax.xyz
dig @1.1.1.1 +short A test.gateway.apps.sno-ai-lab.vanillax.xyz
```

These commands are reads. Do not use `oc debug`, `kubectl apply`, `oc apply`,
Helm install/upgrade, namespace creation, or secret creation during a
read-only recheck.

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
