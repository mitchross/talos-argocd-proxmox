# Inventory

**Start with the [fleet inventory](2026-10-22-fleet-inventory.md)** for every machine,
node and its load today. [Explore the lab](../lab.md) has the interactive map from the
October 15 snapshot. Use [hardware diagnostics](../diagnostics.md) for disk
health and repair evidence. For speed verdicts and upgrade priorities, open
[Audits](../audits/index.md) in the sidebar.

## Fleet inventory — October 22, 2026 (current)

[Open the fleet inventory](2026-10-22-fleet-inventory.md) for every machine and node:
CPU, RAM, load, memory requests, accelerators, Longhorn disks and GitOps health. It is the
first snapshot with three bare-metal minis (`hp-elite-gen13` replaced the `.22` Proxmox host)
and with every non-Wi-Fi data disk in Longhorn.

## Fleet inventory — October 21, 2026

[Open the fleet inventory](2026-10-21-fleet-inventory.md) for every machine and node:
CPU, RAM, load, uptime, memory requests per node, accelerators, Longhorn disks and
GitOps health, with the `.22` HP Elite still a Proxmox host. It is the first snapshot
with the two bare-metal minis and without the retired Dell OptiPlex.

## Full inventory — October 15, 2026

[Open the October 15 inventory](2026-10-15-full-inventory.md) for VM disk paths,
Proxmox storage, physical drives with SMART status, and NAS pools. The explorer
still uses this snapshot. It shows the Dell OptiPlex (now retired) and not the minis.

## Where every disk is

The [disk map](../domains/storage/disk-map.md) is the current, maintained answer
to "which physical disk holds this data, and where should new data go?".

## etcd on the Intel S3610 — October 11, 2026

| Open | What it answers |
| --- | --- |
| [etcd on the Intel S3610](2026-10-11-etcd-on-s3610.md) | How much faster is etcd on an enterprise SSD? What latency should a new control plane match? |

## Storage audit — September 26, 2026

| Open | What it answers |
| --- | --- |
| [Storage audit](2026-09-26-storage-audit.md) | How much do the SSDs write per day? Which disks are full on paper? What is at risk on the NAS? |

## Benchmarks — September 20, 2026

| Open | What it answers |
| --- | --- |
| [Disk and network benchmarks](2026-09-20-capacity-and-benchmarks.md) | Which disk and network paths are fast or slow? Its host list predates the minis and includes the retired Dell. |
| [NAS hardware and performance](../nas-performance.md) | How fast are the pools, how much does RAM help, and what happens with four transfers? |
| [Hardware diagnostics](../diagnostics.md) | How do the new measurements fit the existing disk and repair evidence? |
| [Explore the lab](../lab.md) | What is in each machine? Open its latest measurement alongside the hardware snapshot. |

These are measured snapshots, not live monitoring. Each dataset retains its own
date and test method. New results replace older current recommendations; the
older observations remain available for historical comparison.

Open [audits](../audits/index.md) for prioritized findings, or
[ongoing research](../research/index.md) for changes still being considered.
