# Audits

**Start with the [20 September homelab report](2026-09-20-homelab-report.html).**
It puts the DNS, NAS, Proxmox, NetBird, and TrueNAS-plugin findings in priority
order, with expandable evidence and proposed next steps.

Use the September 20 assessment for current capacity, benchmark and purchasing
recommendations. Older audits remain dated evidence; corresponding findings are
superseded where the newer measurements differ. A recommendation is not a deployed change.

| Assessment | Scope |
| --- | --- |
| [20 September 2026 — homelab decisions](2026-09-20-homelab-report.html) | Remote DNS, measured NAS needs, management options, and small pilots |
| [Proxmox & Kubernetes performance](../inventory/2026-09-20-capacity-and-benchmarks.md) | Disk speeds, fast/slow verdicts, capacity, and consolidation limits |
| [NAS performance & RAM](../nas-performance.md) | Pool speeds, disk versus RAM cache, concurrent transfers, and future hardware needs |
| [5 September 2026 — architecture](2026-09-05-architecture-audit.md) | GitOps, dependencies, recovery, and operational boundaries |
| [5 September 2026 — hardware and placement](2026-09-05-hardware-and-placement-review.md) | Host capacity, disks, and workload placement |

## Past snapshots

These pages record the lab at one point in time. Use the
[fleet inventory](../inventory/2026-10-27-fleet-inventory.md) and
[disk map](../domains/storage/disk-map.md) for current state.

| Snapshot | What it answers |
| --- | --- |
| [Fleet inventory — 22 October](../inventory/2026-10-22-fleet-inventory.md) | Machines, nodes and load after the bare-metal move, before the `proxmox-hp-elite` provider was removed. |
| [Fleet inventory — 21 October](../inventory/2026-10-21-fleet-inventory.md) | Machines, nodes and load while the `.22` HP Elite was still a Proxmox host. |
| [Full inventory — 15 October](../inventory/2026-10-15-full-inventory.md) | VM disk paths, Proxmox storage, physical drives with SMART status, and NAS pools. |
| [etcd on the Intel S3610 — 11 October](../inventory/2026-10-11-etcd-on-s3610.md) | How much faster etcd is on an enterprise SSD, and what latency a new control plane should match. |
| [Storage audit — 26 September](../inventory/2026-09-26-storage-audit.md) | Daily SSD writes, disks full on paper, and NAS risks. |
| [Hardware diagnostics — September](../diagnostics.md) | Disk health and repair evidence from the September inspection. |

The September 20 report is a standalone reading page with its own navigation
and print controls. [Inventory](../inventory/index.md) holds current hardware state;
[ongoing research](../research/index.md) tracks options still under consideration.
