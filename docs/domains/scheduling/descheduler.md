# Descheduler: why pods get moved, and why it matters here

**Purpose:** explain what the descheduler does in this cluster, why it exists, and
how to tell whether it is working.
**Status:** running. Config: `infrastructure/scheduling/descheduler/values.yaml`.

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
- **LowNodeUtilization:** if some nodes are busy (above 70% of memory requests)
  **and** some are quiet (below 55%), move pods from busy to quiet until the busy
  node drops under 70% or the quiet one passes 55%. Memory only: CPU and pod count
  are never tight here. It uses the pods' *requests* (what they reserve), not live
  usage, because requests are what stop new pods from scheduling.

## The guards, and why each exists

| Guard | Why |
|---|---|
| **Pods on `longhorn-flash` or `longhorn-wired-ha` are never moved** | Those classes keep Longhorn data locality on, so a move makes Longhorn copy the whole volume to the new node: exactly the write storm the [disk-write rules](../storage/disk-writes.md) exist to stop. Pods on the plain `longhorn` class (locality off, 1 replica) **may** move: the volume re-attaches over the network and the pod is down for about a minute. Pods with only an `emptyDir` may move too; that is scratch space. |
| `nodeFit` | Only evict a pod if another node can actually run it; otherwise it would bounce back or sit `Pending`. |
| At most 3 evictions per node per run | Rebalancing happens gradually, never as a flood of restarts. |
| PodDisruptionBudgets are respected | An app that declares "keep at least one running" is never taken to zero. |

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

Three nodes are above 70% and none is below 55%, so there is nowhere better to put
anything, and it correctly moves nothing. That signals the cluster is **full on
requests**, not unbalanced. The fix for that is lowering requests (the
[VPA](vpa-and-topology.md) does this over time; check its `minAllowed` floors) or
adding capacity, not tuning the descheduler.

`totalEvicted` above zero, with the named pods landing on quieter nodes, is the
descheduler doing its job. Seeing the same pods evicted every run means the
thresholds fight the scheduler; raise `targetThresholds` or check the pods'
node selectors.

## Pausing it

Set `suspend: true` in `infrastructure/scheduling/descheduler/values.yaml` and let
ArgoCD sync. Pause it during maintenance where you drain nodes on purpose, so it
doesn't start moving pods back before you're done.
