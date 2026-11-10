# Why the descheduler moves pods

The descheduler is a CronJob that evicts a few badly placed pods so that the scheduler can place them again.
This page explains why this cluster runs it, which pods it may move, and how to read a run.
Read it when a pod restarted with no deploy, or when one node is full while another is idle.

The config is `infrastructure/scheduling/descheduler/values.yaml`.

## The problem it solves

Kubernetes decides where a pod runs once, when the pod starts. It does not look at that decision again.

In a homelab that goes wrong often. Reboot one Proxmox host, and every pod on it restarts on the other nodes.
When the host comes back, it is empty.
The nodes that took the extra load stay overloaded, because nothing tells those pods to move back.
After a few reboots or upgrades, one or two nodes carry most of the cluster while another is idle.
New pods then fail to schedule even though spare capacity exists on the idle node.

The [descheduler](https://github.com/kubernetes-sigs/descheduler) corrects that.
Every 30 minutes it looks for pods in the wrong place and evicts a few of them.
The Deployment recreates each evicted pod, and the scheduler places the new pod on a better node.

## What it does here

The CronJob runs two rules.

**RemoveDuplicates.** If two replicas of the same app are on one node, it moves one.
The loss of that node then does not remove every copy.

**LowNodeUtilization.** It acts only when some nodes are busy and some are quiet at the same time.
A busy node is above 65% of memory requests. A quiet node is below 55%.
It moves pods from busy nodes to quiet nodes until the busy node drops under 65% or the quiet node passes 55%.

Two details of LowNodeUtilization matter:

- It counts memory only, because CPU and pod count are never tight here.
- It uses the pods' requests, the amount each pod reserves, not live usage. Requests are what stop new pods from scheduling.

## The guards, and why each exists

| Guard | Why |
|---|---|
| Pods with a PVC on `longhorn-flash` or `longhorn-wired-ha` are never moved | Those classes keep Longhorn data locality on. A move makes Longhorn copy the whole volume to the new node. The [disk-write rules](../storage/disk-writes.md) exist to stop that volume of writes. |
| Pods in `kube-system` and `longhorn-system` are never moved | An eviction of a Longhorn CSI or manager pod restarts attach and backup work across the cluster. `kube-system` pods carry no requests, so an eviction there does not lower the node's usage. |
| `nodeFit` | The descheduler evicts a pod only if another node can run it. Otherwise the pod returns to the same node or stays `Pending`. |
| At most 3 evictions per node per run | Rebalancing is gradual. It does not restart many pods at once. |
| PodDisruptionBudgets are respected | An app that declares "keep at least one running" never drops to zero. |

The protected list in `values.yaml` also names `longhorn-kopiur-staging-local`.

Other pods with storage may move:

- A pod on the plain `longhorn` class (data locality off) may move. The volume attaches again over the network, and the pod is down for about a minute.
- A pod with only an `emptyDir` may move. That volume is scratch space.

Because of the first guard, the Loki and Grafana stack (`longhorn-flash`) and the `longhorn-wired-ha` databases stay where they are.
The descheduler can move everything else a few pods at a time, including databases on the plain `longhorn` class.

## Read a run

```sh
kubectl -n descheduler get jobs
kubectl -n descheduler logs job/<newest-job> | grep -E 'Number of|evicted'
```

Example output:

```
"Number of underutilized nodes" totalNumber=0
"Number of overutilized nodes"  totalNumber=3
"Number of evictions/requests"  totalEvicted=0
```

In this example, three nodes are above 65% and no node is below 55%.
No node is a better place, so the descheduler correctly moves nothing.
The cluster is full on requests. It is not unbalanced.

| What you see | What it means | What to do |
|---|---|---|
| Overutilized nodes, zero underutilized nodes, zero evictions | The cluster is full on requests | Lower requests or add capacity. The [VPA](vpa-and-topology.md) lowers requests over time, so check its `minAllowed` floors. Descheduler tuning does not help |
| `totalEvicted` above zero, and the named pods land on quieter nodes | The descheduler works | Nothing |
| The same pods are evicted every run | The thresholds fight the scheduler | Raise `targetThresholds`, or check the pods' node selectors |

### Underused nodes exist, but no pods move

Look for `Skipping eviction for pod, doesn't tolerate node taint` in the logs.

The descheduler can count a tainted node as underutilized while most pods cannot run there.
`nodeFit` then prevents the eviction, because no other node can run the pod.

If all ordinary workers exceed 65% of memory requests, only the tainted nodes can qualify as destinations.
Higher eviction limits do not remove those taints.
Review [control-plane eligibility](vpa-and-topology.md#control-plane-eligibility) and workload tolerations before you change thresholds.

Keep the Wi-Fi worker's taint, and keep its Longhorn disks disabled.
Permit selected PVC-free workloads there with an explicit Wi-Fi toleration.
Disabled Longhorn disks prevent replica placement. They do not prevent an app from mounting a remote PVC.

## Pause it

Set `suspend: true` in `infrastructure/scheduling/descheduler/values.yaml` and let Argo CD sync.

Pause the descheduler during maintenance when you drain nodes on purpose.
Otherwise it moves pods back before you finish.
