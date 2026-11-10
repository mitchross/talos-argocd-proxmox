# Hardware overview

This section lists the machines in the lab and how they are configured. Use it
to find a machine, check what is inside it, or plan an upgrade.

The live view is the Homelab Guide at `homelab.vanillax.me`. It shows every
device, disk, and benchmark, and it has the rack planner. It answers only on
the home network. The pages below are the public, dated record that the guide
builds from.

| Page | What it answers |
| --- | --- |
| [Fleet inventory](2026-11-03-fleet-inventory.md) | Which machines exist, with their CPU, RAM, PCIe links, measured speed, and power use. |
| [Minis, RAM and M.2 slots](2026-11-05-minis-and-slots.md) | What is inside each mini PC, which M.2 slots are free, and what to buy. |
| [Disk map](../domains/storage/disk-map.md) | Which physical disk holds which data, and where new data goes. |
| [Manage hosts with Ansible](../domains/hosts/physical-hosts-ansible.md) | How to change a setting on a Proxmox host or the Pi. |
| [Bare-metal Talos workers](../domains/hosts/bare-metal-talos.md) | How to add a machine to the cluster without Proxmox. |
| [Power and cost metering](../domains/power/metering.md) | What each machine costs to run, and how to add a smart plug. |

An inventory page is a snapshot from one day. It is not a live dashboard. Each
page states its collection date. Where two pages disagree, the newer page is
correct.

## Older snapshots

These pages stay in the repo because the Homelab Guide cites them as sources.
They are not in the sidebar. Read them only for the detail named here.

| Snapshot | Still useful for |
| --- | --- |
| [Fleet inventory, 27 October 2026](2026-10-27-fleet-inventory.md) | Longhorn disks and requests per node. |
| [Full inventory, 15 October 2026](2026-10-15-full-inventory.md) | VM disk paths, Proxmox storage, SMART status per drive, and NAS pools. |
| [etcd on the Intel S3610, 11 October 2026](2026-10-11-etcd-on-s3610.md) | etcd disk latency on an enterprise SSD. |
| [Capacity and benchmarks, 20 September 2026](2026-09-20-capacity-and-benchmarks.md) | Disk speeds for the Proxmox hosts and Kubernetes volumes. |

Do not move or rename a file in `docs/inventory/` or `docs/assets/` without
updating `scripts/build-lab-data.mjs` in the `homelab-rack-planner` repo. That
script reads them by path.
