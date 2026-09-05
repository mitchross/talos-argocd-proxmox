# Talos upgrade and disk review

Status: upgrade preparation, with a fresh-provisioning problem still open.
No disks have been moved and no live Omni or Talos upgrade was performed during
this review. The [physical inventory](2026-09-05-inventory.md) records the host
and disk measurements; these recommendations do not change the running layout.

## Upgrade findings

The target is Omni/omnictl 1.11.0, provider `v0.2.0-3-g7cefedd`, Talos 1.14.0,
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

The GPU VM's current ephemeral filesystem reports about 447.6 GiB total and
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
