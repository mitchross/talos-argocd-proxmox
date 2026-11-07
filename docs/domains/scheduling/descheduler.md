# Descheduler: why pods get moved, and why it matters here

**Purpose:** what the descheduler does in this cluster, why it exists, and
how to tell whether it works.
**Status:** running. Config: `infrastructure/scheduling/descheduler/values.yaml`.

## The problem it solves

Kubernetes decides where a pod runs **once**, when the pod starts. It never
revisits that decision.

In a homelab, that goes wrong often. Reboot one Proxmox host and every pod on it
restarts on the other nodes. When the host comes back, it is empty. The nodes that
took the extra load stay overloaded, because nothing tells those pods to move
back. After a few reboots or upgrades, one or two nodes carry most of the cluster
while another sits idle. New pods then fail to schedule even though spare capacity
exists somewhere.

The [descheduler](https://github.com/kubernetes-sigs/descheduler) fixes that. Every
30 minutes it looks for pods in the wrong place and evicts a few of them. The
Deployment recreates each evicted pod, and the normal scheduler places the new
pod on a better node.

## What it does here

It runs as a CronJob with two rules:

- **RemoveDuplicates.** If two replicas of the same app land on one node, it moves
  one, so losing that node doesn't take out every copy.
- **LowNodeUtilization.** If some nodes are busy (above 65% of memory requests)
  **and** some are quiet (below 55%), it moves pods from busy to quiet until the busy
  node drops under 65% or the quiet one passes 55%. It counts memory only, because CPU
  and pod count are never tight here. It uses the pods' *requests* (what they reserve),
  not live usage, because requests are what stop new pods from scheduling.

## The guards, and why each exists

| Guard | Why |
|---|---|
| **Pods on `longhorn-flash` or `longhorn-wired-ha` are never moved** | Those classes keep Longhorn data locality on, so a move makes Longhorn copy the whole volume to the new node: exactly the write storm the [disk-write rules](../storage/disk-writes.md) exist to stop. Pods on the plain `longhorn` class (locality off, 1 replica) **may** move: the volume re-attaches over the network and the pod is down for about a minute. Pods with only an `emptyDir` may move too; that is scratch space. |
| `nodeFit` | Evict a pod only if another node can run it. Otherwise it bounces back or sits `Pending`. |
| At most 3 evictions per node per run | Rebalancing is gradual, not a flood of restarts. |
| PodDisruptionBudgets are respected | An app that declares "keep at least one running" never drops to zero. |

Because of the first guard, the Loki and Grafana stack (`longhorn-flash`) and the
`longhorn-wired-ha` databases stay where they are. Everything else, including
databases on the plain `longhorn` class, can be moved a few at a time.

## Reading a run

```sh
kubectl -n descheduler get jobs
kubectl -n descheduler logs job/<newest-job> | grep -E 'Number of|evicted'
```

Example output, and what it means:

```
"Number of underutilized nodes" totalNumber=0
"Number of overutilized nodes"  totalNumber=3
"Number of evictions/requests"  totalEvicted=0
```

Three nodes are above 65% and none is below 55%. Nowhere is better, so it correctly
moves nothing. The cluster is **full on requests**, not unbalanced. To fix that,
lower requests or add capacity. The [VPA](vpa-and-topology.md) lowers requests over
time, so check its `minAllowed` floors. Tuning the descheduler does not help.

`totalEvicted` above zero, with the named pods landing on quieter nodes, means the
descheduler works. If the same pods are evicted every run, the thresholds fight the
scheduler. Raise `targetThresholds` or check the pods' node selectors.

### Underused nodes exist, but no pods move

Check for `Skipping eviction for pod, doesn't tolerate node taint` in the logs.
The descheduler can classify a tainted node as underutilized while most pods
cannot run there. `nodeFit` prevents eviction when no other node can run the pod.

If all ordinary workers exceed 65% memory requests, only the tainted nodes may
qualify as destinations. Raising eviction limits does not remove those taints.
Review [control-plane eligibility](vpa-and-topology.md#control-plane-eligibility)
and workload tolerations before changing thresholds.

Keep the Wi-Fi worker's taint and disabled Longhorn disks. Permit selected
PVC-free workloads with an explicit Wi-Fi toleration. Disabled Longhorn disks
prevent replica placement; they do not prevent an app from mounting a remote PVC.

## Pausing it

Set `suspend: true` in `infrastructure/scheduling/descheduler/values.yaml` and let
ArgoCD sync. Pause it during maintenance when you drain nodes on purpose, so it
doesn't move pods back before you finish.
