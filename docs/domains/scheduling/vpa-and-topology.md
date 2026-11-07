# VPA policy ownership and scheduling

**Purpose:** explain how this cluster sizes pod requests with Vertical Pod
Autoscaler (VPA), where each policy belongs, and how request resizing affects
horizontal scaling and topology.

**Status:** current architecture and operator runbook.

**Scope:** VPA request recommendations and actuation, topology spread,
disruption budgets, and the descheduler that rebalances stateless pods.

## Mental model

VPA is three separate runtime actions:

1. The recommender learns per-container CPU and memory usage.
2. The updater applies `InPlaceOrRecreate` recommendations to existing pods.
3. The admission controller applies recommendations when new pods are created.

Stopping only the updater is therefore **not** a cluster-wide off switch. Admission
can still change new pods. To stop all actuation and keep learning, disable both `updater.enabled` and `admissionController.enabled` in
`infrastructure/scheduling/vertical-pod-autoscaler/values.yaml`; leave the
recommender enabled.

VPA changes requests, not placement. The scheduler evaluates topology spread
only when it schedules a pod, and an in-place resize does not move the pod. A
balanced workload can therefore become imbalanced as requests grow.

## Repository layout

| Owner | Policy location | Why |
|---|---|---|
| User application | `my-apps/<category>/<app>/vpa.yaml` | App deletion prunes its policy; target and sizing review happen together |
| Monitoring application | `monitoring/<app>/vpa.yaml` | Same ownership rule, including Helm-rendered and operator CR targets |
| Bootstrap/system workload | `infrastructure/scheduling/vpa-system-policies/` | Exception for workloads whose owner reconciles at the VPA CRD wave or otherwise cannot safely own the policy after CRD bootstrap |
| VPA controller | `infrastructure/scheduling/vertical-pod-autoscaler/` | Recommender, updater, admission controller, and CRDs at wave 4 |
| VPA monitoring | `infrastructure/scheduling/vertical-pod-autoscaler-observability/` | Optional PodMonitor and alerts at wave 6, after Prometheus CRDs |

The policy object identity is its namespace and name. Keep both unchanged when
moving a policy between Argo applications. The recommender's checkpoints and
in-memory aggregate histories can then reattach after the ownership handoff.
During the one-PR migration, the historical central Application reconciles at
wave 4 and prunes moved policies. Monitoring owners at wave 5 and user
application owners at wave 6 then adopt them. PostHog is a temporary exception.
Its migration hook currently blocks sync, so its policies stay central until
that Application is sync-healthy. Never render two policies that target the
same workload.

The system-policy entrypoint keeps the historical Argo Application name
`vpa-recommendations`. Its file and source path describe the new responsibility.
Keeping the Application identity prevents a cascading delete of every existing
VPA. It carries `SkipDryRunOnMissingResource=true` and
retry settings because it shares wave 4 with the VPA controller on a cold
bootstrap. Infrastructure applications at that same wave remain central unless
they gain an explicitly ordered post-CRD owner.

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

These rules explain that shape:

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
`scripts/vpa-exemptions.yaml`. Prose-only exclusions are not policy.

## Topology and disruption

The active Omni template uses physical-host zone labels:

| Physical host | Talos nodes | Zone |
| --- | --- | --- |
| HP SFF | Control plane and worker | `hp-sff` |
| HP Elite | Worker | `hp-elite` |
| Dell Pro Micro (bare metal) | Worker `mini-pc-dell-ultra-worker` | `mini-pc-dell-ultra` |
| HP Elite Mini 800 G9 (bare metal) | Worker `hp-elite-gen12` | `hp-elite-gen12` |
| Threadripper | GPU worker | `house` |
| Shed HP | Worker behind the media bridge | `shed` |

Cloudflared uses required `DoNotSchedule` spread across eligible
`topology.kubernetes.io/zone` domains, with `nodeTaintsPolicy: Honor` and
rollout-scoped `matchLabelKeys`. Two VMs on the SFF count as one physical host.
Preferred anti-affinity and node affinity favor separate hosts in the `general`
pool. Other eligible workers stay usable when the HPs lack room, and several
tunnel pods can share a surviving host. Verify actual placement. Spread does not
guarantee a different chassis per replica when fewer zones are eligible.

The OpenTelemetry gateway runs two replicas with a required zone spread
(`DoNotSchedule`, `nodeTaintsPolicy: Honor`), a `maxUnavailable: 1` budget and a
preference for the `general` pool. Its pipelines keep no per-trace state, so either
replica can take any request. Check placement with:

```sh
kubectl -n opentelemetry get pods -l app.kubernetes.io/name=otel-gateway-collector -o wide
kubectl get nodes -L topology.kubernetes.io/zone,node.vanillax.dev/pool
```

Match each pod's node to its zone. With at least two eligible zones and enough
capacity, expect two Ready pods on different zones. Reverting the manifest
returns it to one replica. No data moves.

### What each worker is for

The Omni template declares a separate `node.vanillax.dev/pool` label:

| Worker | Pool | Intended job |
|---|---|---|
| HP SFF, HP Elite and the bare-metal minis | `general` | Everyday services and selected application state |
| Threadripper | `gpu` | GPU workloads and selected heavy jobs |
| Shed HP Micro | `edge` | Attached devices and permitted edge jobs |

These labels describe intent. A label alone does not move existing apps or
Longhorn replicas. Cloudflared and the OpenTelemetry gateway use the label as a
soft preference. The separate control-plane scheduling patch is described below.

Check live labels after syncing the Omni template. Merging Git does not change
allocated machines. Finish the active Talos upgrade before applying another
template change. Confirm the Omni sync preview shows the expected label changes
without machine replacement, then check:

```sh
kubectl get nodes -L node.vanillax.dev/pool,topology.kubernetes.io/zone
kubectl -n cloudflared get pods -o wide
```

Expect labels that match the table, and all three tunnel replicas Ready after
the ordinary Deployment rollout. If the labels are not applied yet, preferred
affinity still lets the tunnel pods schedule. Rolling back the Deployment
preference is independent of reverting the Omni labels. A label change does not
drain workers or re-provision disks.

Pair spread with a
`PodDisruptionBudget` on replicated critical workloads, using `maxUnavailable: 1` and
`unhealthyPodEvictionPolicy: AlwaysAllow`. Do not add `minAvailable: 1` to a
single-replica controller: it blocks voluntary Talos drains. The VPA controller
currently runs one replica per component, so its PDBs stay off on purpose.

Topology spread does not rebalance running pods. If request growth repeatedly
fills one node, first correct ceilings and placement constraints.

### Wi-Fi worker eligibility

Keep the HP Micro's `node.vanillax.dev/link=wifi:NoSchedule` taint and both
Longhorn disks unschedulable. Opt in selected PVC-free Deployments with an exact
Wi-Fi toleration. A toleration permits placement; it does not pin the app there.

| Eligible Deployment | Why it fits |
|---|---|
| `excalidraw`, `it-tools`, `vert` | Small browser frontends; Vert's conversion backend stays wired |
| `homepage-public`, `echo-server` | Small web services with no persistent data |
| `radar-ng-web`, `map-styles` | Static frontend and style files; map data and workers stay wired |
| `redlib`, Redlib's `anubis` | Small optional web services with no persistent data |
| `mcp-grafana` | Read-only Grafana tool service with no persistent data |
| `pairdrop` | Web interface and signaling; this deployment disables WebSocket file-transfer fallback |

PVC-free is the first filter. Keep cluster controllers, public tunnel gateways,
databases, builds, conversion backends, and inference workloads on wired nodes.
Remote database calls and high network traffic can make a PVC-free app unsuitable.
ConfigMap and Secret volumes are suitable. Review scratch volume size and write
activity separately. Disabled Longhorn disks do not prevent remote PVC mounts.

After ArgoCD syncs the affected Applications, check pod readiness and placement:

```sh
kubectl get pods -A --field-selector spec.nodeName=talos-prod-cluster-v2-hp-micro-workers-pstbbd -o wide
```

Expect only opted-in applications and existing system or edge pods on HP Micro.
Eligible apps may remain on wired nodes because requests, topology, and affinity
still affect placement. Revert an app's toleration through a PR to remove its
eligibility. The resulting Deployment rollout replaces its pods on eligible nodes.

### Control-plane eligibility

The Omni template's `control-plane-workloads` patch removes the control-plane
`NoSchedule` taint. Application pods can then run without a control-plane
toleration. Existing pods stay in place until a rollout or descheduler eviction.

This is template desired state. The live taint remains until the approved Omni
patch is applied. ArgoCD does not apply Omni templates.

Use the Talos 1.14 `KubeNodeConfig.taints` deletion, not the legacy
`cluster.allowSchedulingOnControlPlanes` field. See the
[Talos control-plane scheduling guide](https://docs.siderolabs.com/talos/v1.14/deploy-and-manage-workloads/workloads-on-controlplane).

Inspect the Omni template diff before applying it. Stop if it includes unrelated
upgrades, machine changes, or resource deletions. Apply only the reviewed
`control-plane-workloads` ConfigPatch when the full template has unrelated drift.

After applying the approved patch, run:

```sh
kubectl get nodes -l node-role.kubernetes.io/control-plane -o custom-columns='NAME:.metadata.name,TAINTS:.spec.taints'
kubectl -n descheduler get jobs
kubectl -n descheduler logs job/<newest-job>
```

Expect the control-plane taint to be absent. Check subsequent descheduler logs
for evictions and verify replacement pods become Ready. Resource requests,
affinity, and PodDisruptionBudgets still restrict placement.

For rollback, restore `node-role.kubernetes.io/control-plane: NoSchedule` in the
same ConfigPatch through a PR. `NoSchedule` blocks new pods but does not evict
existing pods. Review existing placements separately.

### Descheduler: rebalancing movable pods

The scheduler places a pod once. The descheduler moves eligible pods later, so
reboots don't leave some nodes overloaded and others idle. It protects PVCs on
selected storage classes; other PVC-backed pods may move. See
[descheduler](descheduler.md).

The [hardware and placement review](../../audits/2026-09-05-hardware-and-placement-review.md)
proposes workload pools alongside these existing physical-host zones. Pool labels,
new taints and placement migrations in that review are not deployed configuration.

## Verification

Run from the repository root:

```bash
kustomize build infrastructure/scheduling/vertical-pod-autoscaler --enable-helm
kustomize build infrastructure/scheduling/vpa-system-policies
kustomize build infrastructure/scheduling/vertical-pod-autoscaler-observability
python3 scripts/validate-vpa-policies.py /tmp/all-manifests.yaml
```

The last command expects the aggregate render that Cluster CI produces. Success
reports one unique target per VPA and zero errors. Each coverage warning needs
either a new co-located policy or a reasoned machine-readable exemption.

After Argo syncs, verify:

```bash
kubectl get vpa -A
kubectl get vpa -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,MODE:.spec.updatePolicy.updateMode'
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pods -n cloudflared -o wide
kubectl get pdb -n cloudflared
```

Expect active policies in `InPlaceOrRecreate`, the learn-only policy in `Off`,
zone values that match the table after the Omni template syncs, cloudflared
replicas spread when nodes are available, and a PDB allowing at most one
voluntary disruption. A blank zone means the Omni template has not yet reached
that machine set. A Git edit does not label a live Talos node by itself.

## Failure and rollback

- If a moved policy is `SharedResource`, confirm the central wave-4 owner has
  pruned it before a later-wave owner retries. Stop if two policies
  target the same workload.
- If recommendations disappear, confirm the target kind, name and namespace, and
  inspect recommender logs. Do not rename the VPA as a first response.
- If resizing threatens scheduler headroom, disable both updater and admission
  in Git. The recommender keeps learning while the change rolls out.
- Roll back a policy move by restoring its previous owner while preserving its
  namespace/name. Do not delete checkpoints manually.

The sources of truth are the controller
[`values.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/scheduling/vertical-pod-autoscaler/values.yaml),
the rendered-policy validator
[`validate-vpa-policies.py`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/validate-vpa-policies.py),
and the node labels in
[`cluster-template-prod-v2.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template-prod-v2.yaml).
