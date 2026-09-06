# Talos upgrade and disk review

Status: the live Talos 1.14.0 and Kubernetes 1.37.0 upgrades are complete.
Fresh GPU provisioning still needs a disk-selection fix. No disks were moved.
The [physical inventory](2026-09-05-inventory.md) records the host and disk
measurements; the [interactive lab map](../lab.md) includes the verified versions.

## Verified upgrade results

Omni reported Talos complete at **00:55 UTC** and Kubernetes complete at
**00:58 UTC on September 6, 2026**. The owner subsequently rebooted the GPU
machine again. The following checks were taken after it returned, at
**01:48 UTC** (September 5 evening in Detroit).

| Check | Observed result |
|---|---|
| Nodes | All six Ready on Talos 1.14.0 and Kubernetes 1.37.0 |
| Longhorn | 66 attached volumes healthy; 12 detached with unknown robustness; none faulted or degraded |
| Networking | Cilium and Envoy each 6/6; all three Gateways accepted and programmed |
| Storage controllers | TrueNAS CSI nodes 6/6 and controller 1/1; snapshot controller 2/2 |
| GPU | One allocatable NVIDIA GPU; device plugin and llama.cpp Ready |
| Metrics | All 97 Prometheus `up` series were 1, including etcd, Cilium, node-exporter and kube-state-metrics |
| Applications | PostHog, Radar, Loki, Prometheus and Redlib recovered; Flatnotes remains the previously deferred Nomad issue |

Argo reported 96 healthy Applications and one progressing Application
(`my-apps-project-nomad`). `my-apps-immich` and `root` were healthy but OutOfSync;
these checks do not claim every Application has converged. Readiness and storage
health also do not substitute for a full data-integrity check or restore drill.

The last GPU worker lock was removed after its first recovery. All machine sets
then reported zero locked updates. An Omni worker lock did **not** cancel a
Talos upgrade request already in flight; use it to hold subsequent work, and
check the current machine operation before assuming maintenance has stopped.

For a read-only recheck from an authenticated workstation:

```bash
kubectl get nodes -o wide
kubectl get --raw /readyz
kubectl -n longhorn-system get volumes.longhorn.io
omnictl get talosupgradestatuses -o yaml
omnictl get kubernetesupgradestatuses -o yaml
```

Expect Ready nodes, `ok` from the API, healthy attached volumes, and Omni's
`lastupgradeversion` at the intended version with no upgrade error. If a node
or volume regresses, inspect that failure before starting another rollout.
The [recovery runbook](../disaster-recovery.md) owns recovery procedures.

## Upgrade findings

The reviewed target is Omni/omnictl 1.11.0, provider `v0.2.0-3-g7cefedd`, Talos 1.14.0,
and Kubernetes 1.37.0. Upgrade Omni before the provider that uses its new
installation-media API. Check Omni's compatible Kubernetes versions, upgrade
Talos while retaining the current Kubernetes version, verify node readiness,
Cilium, CSI and GPU extensions, then upgrade Kubernetes. A final-target template
is not an instruction to skip these checks.

The install-disk concern applies to **fresh installation**. Omni's resolver
uses the detected system disk on an installed machine. Without an explicit
selection on a fresh machine, it picks the smallest eligible disk. The GPU
class declares a 450 GB primary disk plus 450 GB and 300 GB data disks, so the
default picks the 300 GB flash tier. A per-machine override does not solve
automatic replacements: the provider generates a new UUID, while
`MachineInstallDiskConfig` is keyed by the old machine's UUID.

Do not delete/reprovision the GPU VM or use the full rebuild procedure until
that selection is made deterministic for a new UUID. Changing disk sizes must
also account for the Talos user-volume selectors and Longhorn capacity. No
capacity reduction is included in the upgrade PR.

Sources: [Omni install-disk resolver](https://github.com/siderolabs/omni/blob/v1.11.0/internal/backend/runtime/omni/controllers/omni/installdisk/resolve.go),
[machine-specific template configuration](https://github.com/siderolabs/omni/blob/v1.11.0/client/pkg/template/internal/models/machine.go),
and [provider UUID allocation](https://github.com/siderolabs/omni-infra-provider-proxmox/blob/7cefeddbf2145bc400e3b529e6d5dfe08c27194a/internal/pkg/provider/provision.go).

The active cluster has one control-plane machine on the HP SFF. Deleting it
cannot preserve quorum. A planned reboot temporarily removes the API, and a
failed upgrade needs diagnosis or the [recovery runbook](../disaster-recovery.md),
not a generic machine-delete command. Worker replacements need the same care
with storage: most Longhorn claims have only one copy.

Talos 1.14 moves the default etcd HTTP endpoint, but this repository explicitly
sets `listen-metrics-urls` to port 2381 and Prometheus already uses that port.
Keep this explicit setting and check the `kube-etcd` target after the upgrade.
The [Talos release notes](https://github.com/siderolabs/talos/releases/tag/v1.14.0)
state that a customized metrics listener keeps its configured endpoint.

## Disk placement follow-up

The pre-upgrade GPU filesystem sample reported about 447.6 GiB total and
272.9 GiB free, with 283 GiB of Longhorn volume capacity scheduled there.
Simply changing its boot disk to 128 GiB would not preserve that layout. A
smaller boot disk needs a separate allocation and restore plan for those volumes.
The 300 GiB flash filesystem reports about 151.7 GiB free; its 415 GiB scheduled
figure is logical thin provisioning, not 415 GiB of physical data.

| Host or pool | Verified finding | Next action |
|---|---|---|
| HP SFF control-plane disk | A dedicated 1 TB PNY CS900 holds a 100 GiB VM disk; roughly 831 GiB of its VG was free. Etcd fsync p99 was about 49 ms in the sampled five-minute window. | Prioritize a healthy SSD with power-loss protection for this VM. Confirm latency before and after; free capacity alone does not fix synchronous-write latency. |
| HP Elite worker disk | Intel SSDPEKNW512G8 reported 74% used and no media errors. | Treat this as endurance planning, not proof of a failed disk. Use a replacement with better sustained-write behavior for replicated application state. |
| Threadripper enterprise pool | Two 480 GB HPE SATA SSDs form an mdadm mirror under thick LVM; 300 GB and 120 GB guest disks consume most of it. | Keep the mirror intact while resolving the GPU VM's boot selection. Neither drive is an unused spare. |
| Dell | Temporary exposed motherboard and adapted Apple SSD; the Samsung data SSD had historical CRC errors but no reported media errors. | Avoid making it a required long-term copy of application state. Do not infer an active disk failure from an old CRC counter. |
| TrueNAS boot pool | The HPE 480 GB disk is a member of the boot mirror. | It is not a spare to pull into a worker. Any reuse needs a separate boot-pool replacement plan. |
| TrueNAS RAM and ARC | About 384 GB installed; ARC around 340 GiB, no sampled memory pressure, dedup off. | No evidence supports buying more RAM. A lower ARC cap can be tested later against real NAS latency; the short sample does not establish a minimum RAM requirement. |

Buying one suitable enterprise SSD for the control-plane VM is a more focused
first step than moving working NAS disks. Additional wired storage capacity can
then support selected two-copy Longhorn volumes. Keep caches single-copy and
use the NAS for appropriate shared data and backups, accepting NAS downtime as
the owner intends. NFS-backed data still needs application-specific durability
and recovery decisions; moving every database to the NAS is not an automatic fix.

Before any move, record the source VM disk and pool, confirm a recent successful
Kopiur snapshot for affected application data, and choose either a verified VM
disk migration or a tested restore to new storage. Keep the source until the
replacement passes application checks. Do not combine disk migration with the
Talos rollout: finish one change and verify it before starting the other.

## Live rollout: Longhorn rebuild queue

During the rollout, the Dell drain stopped at its Longhorn instance-manager
PDB. Application pods had left the node, but Longhorn's eviction tickets kept
five volumes attached while their replacement replicas waited to start.

Two parked SwarmUI volumes formed a circular wait: `swarmui-dlbackend` held the
GPU node's only rebuild slot while waiting for a replica on the Elite;
`swarmui-output` held the Elite's only slot while waiting for the GPU node.
Both engines reported no active rebuild. Their original Dell replicas remained
healthy. The V1 volume controller waits for all scheduled, non-failed replicas
to run before updating the engine's replica address map; the replica controller
counts started, not-yet-healthy replicas against the concurrency limit.

The [rebuild setting](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/storage/longhorn/node-failure-settings.yaml)
was raised from one to two slots per node in
[PR #2268](https://github.com/mitchross/talos-argocd-proxmox/pull/2268). This
released the observed circular wait and kept last-replica drain protection in
place. It is a rollout recovery change, not proof that a full restore can sustain two simultaneous
rebuilds or that every possible queue deadlock is eliminated.

After Argo synced, the five held attachments cleared. Longhorn removed its own
instance-manager PDB at **23:16:41 UTC on September 5**; Omni retried and the Dell
returned Ready on Talos 1.14.0 at **23:17:47 UTC**. No PDB, replica, PVC or VM was
manually deleted to make this happen.

If extra concurrency causes faults or excessive latency in a later rollout,
pause further work, inspect the affected engine, and revert the setting through
Git when appropriate. Reverting to one while the circular wait still exists can
restore the blockage. A full Kopiur restore at concurrency two remains untested.

Sources: [Longhorn 1.12.1 replica concurrency controller](https://github.com/longhorn/longhorn-manager/blob/v1.12.1/controller/replica_controller.go#L525),
[volume startup gating](https://github.com/longhorn/longhorn-manager/blob/v1.12.1/controller/volume_controller.go#L2887).

## GPU maintenance still affects ordinary services

The GPU worker's last flash replicas blocked its drain. Thirteen flash-tagged
claims had no eligible second host, including storage used by PostHog, Radar,
Prometheus and Loki. Some of those pods ran elsewhere: moving a pod does not
move the only copy of its data off the GPU host.

The owner rebooted the existing machine. It returned on Talos 1.14.0, and the
temporary Longhorn faults cleared as storage services returned. A later owner
reboot also recovered. No additional drain-policy PR was needed to finish this
upgrade. These recoveries do not establish uninterrupted service during GPU
maintenance or make a forced stop the maintenance procedure.

The remaining work is to give selected ordinary services another eligible
storage host, or define an intentional shutdown and restart sequence for their
consumers. Keep this separate from the fresh-install disk-selection problem:
the successful upgrade reused the existing installation.
