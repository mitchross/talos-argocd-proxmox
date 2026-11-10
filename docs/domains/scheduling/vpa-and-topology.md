# VPA and topology spread

This page explains how the cluster sizes pod requests and how it decides which node a pod may run on.
The Vertical Pod Autoscaler (VPA) changes the CPU and memory a pod requests.
Topology spread, node labels, and taints control placement.
Read it before you add a `vpa.yaml`, add replicas to a critical workload, or let an app run on the Wi-Fi or control-plane node.

## How VPA works

A request is the amount of CPU or memory a pod reserves on a node. The scheduler uses requests to decide whether a pod fits.

VPA has three components, and each one does a separate job:

1. The recommender learns the CPU and memory usage of each container.
2. The updater applies `InPlaceOrRecreate` recommendations to existing pods.
3. The admission controller applies recommendations when new pods are created.

**Stopping only the updater does not turn VPA off.** The admission controller can still change new pods.
To stop all changes and keep learning, disable both `updater.enabled` and `admissionController.enabled` in
`infrastructure/scheduling/vertical-pod-autoscaler/values.yaml`. Leave the recommender enabled.

VPA changes requests, not placement.
The scheduler evaluates topology spread only when it schedules a pod, and an in-place resize does not move the pod.
A balanced workload can therefore become unbalanced as requests grow.

## Where each policy lives

A VPA policy lives next to the workload it sizes.
Argo CD then prunes the policy when the app is deleted, and one review covers the target and its sizing.

| Owner | Policy location | Why |
|---|---|---|
| User application | `my-apps/<category>/<app>/vpa.yaml` | App deletion prunes its policy; target and sizing review happen together |
| Monitoring application | `monitoring/<category>/<app>/vpa.yaml` | Same ownership rule, including Helm-rendered and operator CR targets |
| Bootstrap/system workload | `infrastructure/scheduling/vpa-system-policies/` | Exception for workloads whose owner reconciles at the VPA CRD wave or otherwise cannot safely own the policy after CRD bootstrap |
| VPA controller | `infrastructure/scheduling/vertical-pod-autoscaler/` | Recommender, updater, admission controller, and CRDs at wave 4 |
| VPA monitoring | `infrastructure/scheduling/vertical-pod-autoscaler-observability/` | Optional PodMonitor and alerts at wave 6, after Prometheus CRDs |

### The system-policy Application

The entrypoint for `vpa-system-policies/` creates an Argo CD Application named `vpa-recommendations`.
The name does not match the folder. **Do not rename the Application.**
A rename replaces the Application, and the cascade delete removes every VPA it owns.

The Application carries `SkipDryRunOnMissingResource=true` and retry settings.
It shares wave 4 with the VPA controller, so on a cold bootstrap the VPA CRDs can be absent on the first attempt.

Infrastructure applications at wave 4 keep their policies in this central folder.
Move one out only when it gains an owner that is explicitly ordered after the CRDs.

Some PostHog policies are also in this folder, in `posthog-policies.yaml`.
They stay there while the PostHog Application's migration hook blocks its sync.
Move them to the PostHog app folder after that Application syncs cleanly.

### Move a policy between Applications

The identity of a policy is its namespace and name. Keep both unchanged when you move a policy.
The recommender's checkpoints and in-memory histories then attach to the policy again after the move.

**Never render two policies that target the same workload.**

Make the move in one PR. Remove the policy from the old owner and add it to the new owner.
The central Application reconciles at wave 4 and prunes the policy.
A monitoring owner at wave 5, or a user application owner at wave 6, then adopts it.

## Policy contract

Active policies use this shape:

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

Each field has a reason:

- `RequestsOnly` leaves the limits declared in Git as the hard runtime boundary.
- `minReplicas: 1` is required because most workloads here have a single replica.
- `maxAllowed` applies **per container**, not per pod. A wildcard 2 GiB ceiling on a three-container pod permits up to 6 GiB. For a multi-container pod, name each workload container and set fixed-size sidecars to `mode: Off`.
- `Off` is for learn-only policies, such as a scale-swap workload.

### Do not let VPA control CPU under a CPU autoscaler

A CPU-utilization HPA divides usage by the CPU request.
A VPA that controls CPU on the same target changes that divisor, so the two autoscalers move each other.
The supported pairing is a CPU HPA plus a memory-only VPA.

### What CI checks

`scripts/validate-vpa-policies.py` reads the rendered manifests.
It rejects missing targets, duplicate targets, unsupported modes, unsafe CPU HPA overlap, and active policies without the safety fields.
It warns about uncovered workloads and wildcard ceilings.

Record a reviewed exclusion in `scripts/vpa-exemptions.yaml`. An exclusion that exists only in prose is not policy.

## Zones and pools

The Omni template puts two labels on each node.
`topology.kubernetes.io/zone` names the physical host, so that spread rules can separate replicas by host.
`node.vanillax.dev/pool` names the job the worker is for.

| Physical host | Talos nodes | Zone | Pool | Intended job |
| --- | --- | --- | --- | --- |
| HP SFF | Control plane and worker | `hp-sff` | `general` (worker) | Everyday services and selected application state |
| HP Elite | Worker | `hp-elite` | `general` | Everyday services and selected application state |
| Dell Pro Micro (bare metal) | Worker `mini-pc-dell-ultra-worker` | `mini-pc-dell-ultra` | `general` | Everyday services and selected application state |
| HP Elite Mini 800 G9 (bare metal) | Worker `hp-elite-gen12` | `hp-elite-gen12` | `general` | Everyday services and selected application state |
| TrueNAS DL360 (VM) | Worker `truenas-worker-01` | `truenas` | `general` | Everyday services and selected application state |
| Threadripper | GPU worker | `house` | `gpu` | GPU workloads and selected heavy jobs |
| Shed HP Micro | Worker behind the media bridge | `shed` | `edge` | Attached devices and permitted edge jobs |

The two VMs on the HP SFF share one zone, so spread rules count them as one physical host.
The [fleet inventory](../../inventory/2026-11-03-fleet-inventory.md) has the hardware detail for each machine.

The pool label describes intent. A label alone does not move existing apps or Longhorn replicas.
Cloudflared and the OpenTelemetry gateway use the pool label as a soft preference.

### Apply and check label changes

A merge to Git does not change allocated machines. Argo CD does not apply Omni templates.
A person must sync the Omni template.

1. Do not apply a template change while a Talos upgrade is in progress.
2. Confirm that the Omni sync preview shows the expected label changes and no machine replacement.
3. Sync the template.
4. Check the live labels and the tunnel pods:

```sh
kubectl get nodes -L node.vanillax.dev/pool,topology.kubernetes.io/zone
kubectl -n cloudflared get pods -o wide
```

Expect labels that match the table, and all three tunnel replicas Ready after the ordinary Deployment rollout.
A blank zone means that the Omni template has not reached that machine set.

If the labels are not applied yet, preferred affinity still lets the tunnel pods schedule.
A label change does not drain workers or re-provision disks.
A rollback of the Deployment preference is independent of a revert of the Omni labels.

## Replicated workloads: spread and disruption budgets

### Cloudflared

Cloudflared uses a required `DoNotSchedule` spread across eligible `topology.kubernetes.io/zone` domains.
It sets `nodeTaintsPolicy: Honor` and rollout-scoped `matchLabelKeys`.
Preferred anti-affinity and node affinity favor separate hosts in the `general` pool.

Other eligible workers stay usable when the HP hosts lack room, and several tunnel pods can share a surviving host.
Verify the actual placement. Spread does not guarantee a different chassis per replica when fewer zones are eligible.

### OpenTelemetry gateway

The OpenTelemetry gateway runs two replicas with a required zone spread (`DoNotSchedule`, `nodeTaintsPolicy: Honor`).
It has a `maxUnavailable: 1` budget and a preference for the `general` pool.
Its pipelines keep no per-trace state, so either replica can take any request.

Check placement:

```sh
kubectl -n opentelemetry get pods -l app.kubernetes.io/name=otel-gateway-collector -o wide
kubectl get nodes -L topology.kubernetes.io/zone,node.vanillax.dev/pool
```

Match each pod's node to its zone.
With at least two eligible zones and enough capacity, expect two Ready pods on different zones.
A revert of the manifest returns the gateway to one replica. No data moves.

### Disruption budgets

Pair spread with a `PodDisruptionBudget` on replicated critical workloads.
Use `maxUnavailable: 1` and `unhealthyPodEvictionPolicy: AlwaysAllow`.

**Do not add `minAvailable: 1` to a single-replica controller.** It blocks voluntary Talos drains.
The VPA controller runs one replica per component, so its PDBs stay off on purpose.

Topology spread does not rebalance running pods.
If request growth fills one node again and again, correct the ceilings and placement constraints first.

## Wi-Fi worker eligibility

The shed HP Micro reaches the LAN over Wi-Fi.
Keep its `node.vanillax.dev/link=wifi:NoSchedule` taint, and keep both of its Longhorn disks unschedulable.

To let an app run there, add an exact Wi-Fi toleration to a selected PVC-free Deployment.
A toleration permits placement. It does not pin the app to that node.

| Eligible Deployment | Why it fits |
|---|---|
| `excalidraw`, `it-tools`, `vert` | Small browser frontends; Vert's conversion backend stays wired |
| `homepage-public`, `echo-server` | Small web services with no persistent data |
| `radar-ng-web`, `map-styles` | Static frontend and style files; map data and workers stay wired |
| `redlib`, Redlib's `anubis` | Small optional web services with no persistent data |
| `mcp-grafana` | Read-only Grafana tool service with no persistent data |
| `pairdrop` | Web interface and signaling; this deployment disables WebSocket file-transfer fallback |

Home Assistant and Intercept also carry the toleration.
Each one has a node selector for its USB radio, so it follows the node that has the device.

Use these rules to decide whether an app is suitable:

- PVC-free is the first filter. Disabled Longhorn disks do not prevent a remote PVC mount.
- Keep cluster controllers, public tunnel gateways, databases, builds, conversion backends, and inference workloads on wired nodes.
- Remote database calls and high network traffic can make a PVC-free app unsuitable.
- ConfigMap and Secret volumes are suitable.
- Review the size and write activity of a scratch volume separately.

After Argo CD syncs the affected Applications, check pod readiness and placement:

```sh
kubectl get pods -A --field-selector spec.nodeName=talos-prod-cluster-v2-hp-micro-workers-pstbbd -o wide
```

The node name changes when Omni replaces the machine.
Run `kubectl get nodes -l node.vanillax.dev/link=wifi` to get the current name.

Expect only opted-in apps and existing system or edge pods on the HP Micro.
An eligible app can stay on a wired node, because requests, topology, and affinity still affect placement.

To remove an app's eligibility, revert its toleration through a PR.
The Deployment rollout then replaces its pods on eligible nodes.

## Control-plane eligibility

The Omni template's `control-plane-workloads` patch removes the control-plane `NoSchedule` taint.
Application pods can then run on the control-plane node without a control-plane toleration.
Existing pods stay in place until a rollout or a descheduler eviction.

The patch is template desired state. The live taint remains until a person applies the approved Omni patch.
Argo CD does not apply Omni templates.

Use the Talos 1.14 `KubeNodeConfig.taints` deletion, not the legacy `cluster.allowSchedulingOnControlPlanes` field.
See the [Talos control-plane scheduling guide](https://docs.siderolabs.com/talos/v1.14/deploy-and-manage-workloads/workloads-on-controlplane).

### Apply the patch

1. Inspect the Omni template diff. Stop if it includes unrelated upgrades, machine changes, or resource deletions.
2. If the full template has unrelated drift, apply only the reviewed `control-plane-workloads` ConfigPatch.
3. After the approved patch is applied, run:

```sh
kubectl get nodes -l node-role.kubernetes.io/control-plane -o custom-columns='NAME:.metadata.name,TAINTS:.spec.taints'
kubectl -n descheduler get jobs
kubectl -n descheduler logs job/<newest-job>
```

Expect the control-plane taint to be absent.
Check the next descheduler logs for evictions, and verify that the replacement pods become Ready.
Resource requests, affinity, and PodDisruptionBudgets still restrict placement.

### Roll back

Restore `node-role.kubernetes.io/control-plane: NoSchedule` in the same ConfigPatch through a PR.
`NoSchedule` blocks new pods but does not evict existing pods. Review existing placements separately.

## Descheduler: rebalancing movable pods

The scheduler places a pod once. The descheduler moves eligible pods later, so that reboots do not leave some nodes overloaded and others idle.
It protects pods whose PVCs use selected storage classes. Other PVC-backed pods may move.
See [Why the descheduler moves pods](descheduler.md).

## Verification

Run these commands from the repository root:

```bash
kustomize build infrastructure/scheduling/vertical-pod-autoscaler --enable-helm
kustomize build infrastructure/scheduling/vpa-system-policies
kustomize build infrastructure/scheduling/vertical-pod-autoscaler-observability
python3 scripts/validate-vpa-policies.py /tmp/all-manifests.yaml
```

The last command expects the aggregate render that Cluster CI produces.
Success reports one unique target per VPA and zero errors.
Each coverage warning needs either a co-located policy or a reasoned entry in `scripts/vpa-exemptions.yaml`.

After Argo CD syncs, verify the live state:

```bash
kubectl get vpa -A
kubectl get vpa -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,MODE:.spec.updatePolicy.updateMode'
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pods -n cloudflared -o wide
kubectl get pdb -n cloudflared
```

Expect these results:

- Active policies are in `InPlaceOrRecreate`, and learn-only policies are in `Off`.
- Zone values match the table after the Omni template syncs.
- Cloudflared replicas are spread when nodes are available.
- The PDB allows at most one voluntary disruption.

A blank zone means that the Omni template has not reached that machine set.
A Git edit alone does not label a live Talos node.

## Failure and rollback

| Symptom | What to do |
|---|---|
| A moved policy reports `SharedResource` | Confirm that the central wave-4 owner has pruned it before the later-wave owner retries. Stop if two policies target the same workload |
| Recommendations disappear | Confirm the target kind, name, and namespace, and inspect the recommender logs. Do not rename the VPA as a first response |
| Resizing threatens scheduler headroom | Disable both the updater and the admission controller in Git. The recommender keeps learning while the change rolls out |
| A policy move must be reverted | Restore the previous owner and keep the namespace and name. Do not delete checkpoints by hand |

## Sources of truth

- The controller [`values.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/scheduling/vertical-pod-autoscaler/values.yaml).
- The rendered-policy validator [`validate-vpa-policies.py`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/scripts/validate-vpa-policies.py).
- The node labels in [`cluster-template-prod-v2.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/cluster-template-prod-v2.yaml).
