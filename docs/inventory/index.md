# Inventory

This section shows what the lab runs now. Start with the current snapshot; older pages are listed
under [History](#history).

| Page | What it answers |
| --- | --- |
| [Fleet inventory — 3 November](2026-11-03-fleet-inventory.md) | **Current.** Which machines exist, their RAM and PCIe links, NVMe and RAM speed, power per plug, and how loaded the nodes are. |
| [Minis, RAM and M.2 slots — 5 November](2026-11-05-minis-and-slots.md) | **New.** What is inside each office mini, which M.2 slots are free across the fleet, and the buy list. |
| [Explore the lab](../lab.md) | What is inside each machine, as an interactive map. Its data predates the bare-metal minis. |
| [Disk map](../domains/storage/disk-map.md) | Which physical disk holds which data, and where new data should go. |

For speed verdicts and upgrade priorities, open [Audits](../audits/index.md). For changes still
being considered, open [ongoing research](../research/index.md).

## History

Each page is a dated snapshot. The current page wins where they disagree.

| Snapshot | Still useful for |
| --- | --- |
| [Fleet inventory — 27 October](2026-10-27-fleet-inventory.md) | Per-node Longhorn disks and requests, and the retired `proxmox-hp-elite` provider. |
| [Full inventory — 15 October](2026-10-15-full-inventory.md) | VM disk paths, Proxmox storage, drives with SMART status, NAS pools. |
| [etcd on the Intel S3610 — 11 October](2026-10-11-etcd-on-s3610.md) | How much faster etcd is on an enterprise SSD. |
| [Storage audit — 26 September](2026-09-26-storage-audit.md) | Daily SSD writes and NAS risks. |
| [Capacity and benchmarks — 20 September](2026-09-20-capacity-and-benchmarks.md) | Disk speeds and fast/slow verdicts for the Proxmox hosts and volumes. |

The 21 and 22 October snapshots were deleted. Their content is in git history.
