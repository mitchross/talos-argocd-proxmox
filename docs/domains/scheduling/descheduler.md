# Descheduler: why pods get moved, and why it matters here

**Purpose:** explain what the descheduler does in this cluster, why it exists, and
how to tell whether it is working.
**Status:** running. Config: `infrastructure/controllers/descheduler/values.yaml`.

## The problem it solves

Kubernetes decides where a pod runs **once**, when the pod starts. It never
revisits that decision.

In a homelab, that goes wrong constantly. Reboot one Proxmox host and every pod
on it restarts on the other nodes. When the host comes back, it is empty, and the
nodes that took the extra load stay overloaded, because nothing tells those pods
to move back. After a few reboots or upgrades, one or two nodes carry most of
the cluster while another sits idle, and new pods fail to schedule even though
there is spare capacity somewhere.

The [descheduler](https://github.com/kubernetes-sigs/descheduler) fixes that. Every
30 minutes it looks for pods in the wrong place and evicts a few of them. Each
evicted pod is recreated by its Deployment, and the normal scheduler places the
new one on a better node.

## What it does here

It runs as a CronJob with two rules:

- **RemoveDuplicates:** if two replicas of the same app ended up on one node, move
  one, so losing that node doesn't take out every copy.
- **LowNodeUtilization:** if some nodes are busy (above 60% of CPU, memory or pod
  count) **and** some are quiet (below 25%), move pods from busy to quiet. It uses
  the pods' *requests* (what they reserve), not live usage.

## The guards, and why each exists

| Guard | Why |
|---|---|
| **Pods with a PVC are never moved** | A pod with a `ReadWriteOnce` volume goes down while the volume detaches and re-attaches on the new node. For the `longhorn-flash` and `longhorn-wired-ha` classes, which keep Longhorn data locality on, the move also makes Longhorn copy the whole volume to the new node: exactly the kind of write storm the [disk-write rules](../storage/disk-writes.md) exist to stop. |
| `nodeFit` | Only evict a pod if another node can actually run it; otherwise it would bounce back or sit `Pending`. |
| At most 3 evictions per node per run | Rebalancing happens gradually, never as a flood of restarts. |
| PodDisruptionBudgets are respected | An app that declares "keep at least one running" is never taken to zero. |

Because of the first guard, databases and other stateful apps stay where they are.
If one of those nodes is badly overloaded, move a stateful app by hand during a
quiet moment.

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

Three nodes are above 60% and none is below 25%, so there is nowhere better to put
anything, and it correctly moves nothing. That signals the cluster is **full on
requests**, not unbalanced. The fix for that is lowering requests (the
[VPA](vpa-and-topology.md) does this over time) or adding capacity, not tuning
the descheduler.

`totalEvicted` above zero, with the named pods landing on quieter nodes, is the
descheduler doing its job. Seeing the same pods evicted every run means the
thresholds fight the scheduler; raise `targetThresholds` or check the pods'
node selectors.

## Pausing it

Set `suspend: true` in `infrastructure/controllers/descheduler/values.yaml` and let
ArgoCD sync. Pause it during maintenance where you drain nodes on purpose, so it
doesn't start moving pods back before you're done.
