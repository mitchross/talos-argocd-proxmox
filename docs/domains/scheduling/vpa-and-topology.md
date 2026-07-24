# VPA policy ownership and scheduling

**Purpose:** explain how this cluster sizes pod requests with Vertical Pod
Autoscaler (VPA), where each policy belongs, and how request resizing interacts
with horizontal scaling and topology.

**Status:** current architecture and operator runbook.

**Scope:** VPA request recommendations/actuation, topology spread, and
disruption budgets. A descheduler is deliberately not installed: eviction-based
rebalancing needs a separate policy review because many workloads mount
ReadWriteOnce volumes.

## Mental model

VPA is three separate runtime actions:

1. The recommender learns per-container CPU and memory usage.
2. The updater applies `InPlaceOrRecreate` recommendations to existing pods.
3. The admission controller applies recommendations when new pods are created.

Stopping only the updater is therefore **not** a cluster-wide off switch. New
pods can still be changed by admission. To stop all actuation while preserving
learning, disable both `updater.enabled` and `admissionController.enabled` in
`infrastructure/controllers/vertical-pod-autoscaler/values.yaml`; leave the
recommender enabled.

VPA changes requests, not placement. The scheduler evaluates topology spread
only when a pod is scheduled, and an in-place resize intentionally does not move
the pod. A balanced workload can therefore become imbalanced as requests grow.

## Repository layout

| Owner | Policy location | Why |
|---|---|---|
| User application | `my-apps/<category>/<app>/vpa.yaml` | App deletion prunes its policy; target and sizing review happen together |
| Monitoring application | `monitoring/<app>/vpa.yaml` | Same ownership rule, including Helm-rendered and operator CR targets |
| Bootstrap/system workload | `infrastructure/controllers/vpa-system-policies/` | Small explicit exception for workloads without a suitable co-located wave-5/6 owner |
| VPA controller | `infrastructure/controllers/vertical-pod-autoscaler/` | Recommender, updater, admission controller, and CRDs at wave 4 |
| VPA monitoring | `infrastructure/controllers/vertical-pod-autoscaler-observability/` | Optional PodMonitor and alerts at wave 6, after Prometheus CRDs |

The policy object identity is its namespace and name. Keep both unchanged when
moving a policy between Argo applications. The recommender's checkpoints and
in-memory aggregate histories can then reattach after the ownership handoff.
Argo's `FailOnSharedResource=true` may make the new owner retry once while the
old owner prunes; that retry is expected, but two rendered policies targeting
the same workload are not.

The system-policy entrypoint intentionally retains the historical Argo
Application name `vpa-recommendations` for this one-step migration. Its file and
source path describe the new responsibility; preserving the Application
identity prevents a cascading delete of every existing VPA.

## Policy contract

Active policies use:

```yaml
updatePolicy:
  updateMode: InPlaceOrRecreate
  minReplicas: 1
resourcePolicy:
  containerPolicies:
    - containerName: app
      controlledResources: ["cpu", "memory"]
      controlledValues: RequestsOnly
      maxAllowed:
        cpu: "2"
        memory: 4Gi
```

The rules behind that shape are:

- `RequestsOnly` leaves Git-declared limits as the hard runtime boundary.
- `minReplicas: 1` is required because this cluster is mostly single replica.
- `maxAllowed` is **per container**, not per pod. A wildcard 2 GiB ceiling on a
  three-container pod permits up to 6 GiB. Multi-container workloads therefore
  name their workload containers and use `mode: Off` for fixed-size sidecars.
- A CPU-utilization HPA divides usage by the CPU request. A VPA must not control
  CPU on that same target because it moves the HPA denominator. The supported
  pairing is CPU HPA plus memory-only VPA.
- `Off` is reserved for learn-only policies such as a scale-swap workload.

The rendered-manifest check in `scripts/validate-vpa-policies.py` rejects
missing targets, duplicate targets, unsupported modes, unsafe CPU HPA overlap,
and active policies without the safety fields. It warns about uncovered
workloads and wildcard ceilings. Reviewed exclusions live in
`scripts/vpa-exemptions.yaml`; prose-only exclusions are not policy.

## Topology and disruption

The Omni template assigns every node a zone: the Threadripper control plane and
RTX 3090 worker are `house`, and the separate Dell worker is `yard`.
Cloudflared uses a soft `ScheduleAnyway` hostname constraint. Hostname spread
works immediately on every Kubernetes node; zone labels are declarative in the
Omni template but take effect only after that template is synced. Soft spread
preserves availability during a node outage while preferring an even placement.

Replicated critical workloads should pair spread with a
`PodDisruptionBudget` using `maxUnavailable: 1` and
`unhealthyPodEvictionPolicy: AlwaysAllow`. Do not add `minAvailable: 1` to a
single-replica controller: it blocks voluntary Talos drains. The VPA controller
currently runs one replica per component, so its PDBs intentionally remain off.

Topology spread is not a rebalance loop. If request growth repeatedly fills one
node, first correct ceilings and placement constraints. Evaluate a descheduler
only after classifying RWO workloads and defining which pods may be evicted.

## Verification

Run from the repository root:

```bash
kustomize build infrastructure/controllers/vertical-pod-autoscaler --enable-helm
kustomize build infrastructure/controllers/vpa-system-policies
kustomize build infrastructure/controllers/vertical-pod-autoscaler-observability
python3 scripts/validate-vpa-policies.py /tmp/all-manifests.yaml
```

The last command expects the aggregate render produced by Cluster CI. Success
reports one unique target per VPA and zero errors. Coverage warnings require
either a new co-located policy or a reasoned machine-readable exemption.

After Argo syncs, verify:

```bash
kubectl get vpa -A
kubectl get vpa -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,MODE:.spec.updatePolicy.updateMode'
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pods -n cloudflared -o wide
kubectl get pdb -n cloudflared
```

Expected results are active policies in `InPlaceOrRecreate`, the learn-only
policy in `Off`, zone values `house`/`yard` after the Omni template is synced,
cloudflared replicas spread when nodes are available, and a PDB allowing at
most one voluntary disruption. A blank zone means the Omni template has not
yet been applied to that machine set; do not assume the Git edit labels a live
Talos node by itself.

## Failure and rollback

- If a moved policy is `SharedResource`, wait for the old Argo application to
  prune and let the automated retry run. Stop if two policies target the same
  workload.
- If recommendations disappear, confirm the target kind/name/namespace and
  inspect recommender logs. Do not rename the VPA as a first response.
- If resizing threatens scheduler headroom, disable both updater and admission
  in Git. The recommender continues learning while the change rolls out.
- Roll back a policy move by restoring its previous owner while preserving its
  namespace/name. Do not delete checkpoints manually.

Sources of truth are the controller
[`values.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/vertical-pod-autoscaler/values.yaml),
the rendered-policy validator
[`validate-vpa-policies.py`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/validate-vpa-policies.py),
and the node labels in
[`cluster-template-singlenode-gpu.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template-singlenode-gpu.yaml).
