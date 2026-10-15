# Full infrastructure inventory — October 15, 2026

**Status:** dated, read-only inventory. This replaces the September hardware snapshot in [Explore the lab](../lab.md).

Collection: approximately 04:00–04:10 UTC; LXC configuration checked at 04:12 UTC. Kubernetes, Talos and host queries are separate samples, not an atomic snapshot.

## Coverage and limits

- Seven physical machines: five Proxmox hosts, TrueNAS and the management Pi.
- Seven Proxmox VMs: six running Talos VMs and one stopped Kali VM. Elite also runs LXC 101, Proxmox Datacenter Manager.
- One additional stopped TrueNAS VM; three running TrueNAS apps and nine running Pi containers.
- Twenty-six visible physical drives. The missing Dell T-FORCE is excluded. NAS zvols and guest disks are excluded.
- All six Kubernetes nodes reported Ready: Talos v1.14.2, Kubernetes v1.37.1, containerd 2.3.6.
- All 85 PVCs were Bound. Longhorn reported 65 healthy attached volumes and seven detached volumes with unknown robustness.
- Argo CD reported 97 Healthy applications and one Degraded application: `my-apps-wyze-bridge`.

All 26 visible physical drives reported passing SMART status. NAS HDD temperatures ranged from 32 to 50 °C.

A Ready node, mounted filesystem or passing SMART status does not prove application health or successful storage I/O.
No benchmarks, SMART self-tests, filesystem repairs, backup restores or infrastructure changes were performed.

## Changes and findings

1. **Dell storage mismatch:** Proxmox lists `dell-ssd-vmstore` inactive; its VG and physical T-FORCE disk are absent.
   VM 100 still declares its 400 GiB `scsi1`; Talos still reports the XFS mount and Longhorn still reports free capacity.
   Host logs record an ATA link loss and removal of `sda`. This audit does not establish the cause or data integrity.
   [PR #2946](https://github.com/mitchross/talos-argocd-proxmox/pull/2946) records the T-FORCE replacement, preserving the same VM and Longhorn names.
2. **SFF control plane:** the Intel S3610 now backs VM 101. One PNY SSD is an orphan PV outside any VG.
3. **Dell Apple SSD:** the 220 GiB guest disk backs the separate `dell-apple` Longhorn path.
4. **GPU host:** two RTX 3090 PCI devices are mapped into the Talos VM. Its HPE RAID1 reports both members present (`[UU]`).
5. **NAS:** all four imported pools report ONLINE with no known data errors. The Samsung 850 EVO is visible outside imported pools.
   PR #2946 records its retirement after failed load tests; its current SMART pass does not reverse that finding.
6. **Elite endurance:** Intel 660p reports 76% used and zero NVMe media errors. This is an endurance indicator, not a failure probability.
7. **NAS replication:** the local replication task is enabled without a schedule; its last recorded completion remains May 2025.
   This audit does not establish any off-box backup copy.
8. **Wyze Bridge:** Argo health cites ExternalSecret `wyze-web-session-seed`. This audit does not diagnose its cause.

## Hosts

RAM below is kernel-visible capacity. Configured VM RAM appears separately.

| Host | Address | CPU | Visible RAM GiB | Available RAM GiB | Software |
|---|---|---|---:|---:|---|
| HP SFF | 192.168.10.21 | Intel(R) Core(TM) i5-8500 CPU @ 3.00GHz · 6 threads | 62.6 | 10.0 | pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve) |
| HP Elite Mini | 192.168.10.22 | 13th Gen Intel(R) Core(TM) i5-13500T · 20 threads | 30.6 | 2.0 | pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve) |
| Threadripper | 192.168.10.14 | AMD Ryzen Threadripper 2950X 16-Core Processor · 32 threads | 125.7 | 19.8 | pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve) |
| Dell OptiPlex | 192.168.10.16 | Intel(R) Core(TM) i5-8500 CPU @ 3.00GHz · 6 threads | 39.0 | 6.7 | pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-23-pve) |
| Shed HP Mini | 192.168.10.20 | Intel(R) Core(TM) i5-8500T CPU @ 2.10GHz · 6 threads | 31.1 | 24.0 | pve-manager/9.2.21/4f6e0ac86f9e8c7f (running kernel: 7.0.14-20-pve) |
| Omni / DNS Pi | 192.168.10.15 | Cortex-A76 · 4 threads | 7.7 | 5.7 | Ubuntu 26.04 LTS |
| TrueNAS | 192.168.10.133 | Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz · 28 threads | 377.6 | 283.5 | TrueNAS-28.0.0-MASTER+20261012-230219 |

## Virtual machines

VM IDs are local to each host. NAS VM 5 is separate from the six active Talos nodes.

| Host | VM | Name | State | vCPU | RAM MiB | Node IP |
|---|---|---|---|---:|---:|---|
| sff | 100 | `talos-prod-cluster-v2-hp-sff-workers-h76ncc` | running | 6 | 40960 | 192.168.10.173 |
| sff | 101 | `talos-prod-cluster-v2-control-planes-7mxjxv` | running | 4 | 12288 | 192.168.10.94 |
| elite | 100 | `talos-prod-cluster-v2-hp-elite-workers-l5zlgr` | running | 16 | 26624 | 192.168.10.129 |
| gpu | 100 | `talos-prod-cluster-v2-gpu-workers-jxfkdr` | running | 30 | 102400 | 192.168.10.187 |
| gpu | 102 | `kali-linux` | stopped | 4 | 12000 | Not collected |
| dell | 100 | `talos-prod-cluster-v2-dell-workers-2jfrb8` | running | 6 | 30720 | 192.168.10.84 |
| shed | 100 | `talos-prod-cluster-v2-hp-micro-workers-pstbbd` | running | 4 | 12288 | 192.168.10.128 |
| nas | 5 | `talos_prod_control_03` | STOPPED; autostart false | 2 | 8000 | Not collected |

## LXC guest

Elite runs `proxmox-datacenter-manager` as unprivileged Debian container 101 with autostart enabled.
It has 2 vCPU, 2,048 MiB RAM, 512 MiB swap and a 10 GiB root filesystem.
The backing volume is `hp-elite-vmstore:vm-101-disk-0`, on the Intel 660p.
Its network uses DHCP on `vmbr0`; the guest address was not collected.

The stopped NAS VM uses `/dev/zvol/Backup10T/virtual-machine/talos_prod_control_03-f06my4`.
Its installation ISO is also on `Backup10T`; sanitized paths appear in the inventory JSON.

## Physical drives

Capacity uses decimal GB. Device names can change after reconnecting hardware.

| Host | Device | Model | GB | Path / role | SMART and health |
|---|---|---|---:|---|---|
| sff | sda | PNY CS900 1TB SSD | 1000.2 | No volume group | SMART overall passed; 33 °C at collection. |
| sff | sdb | INTEL SSDSC2BX400G4R | 400.1 | hp-sff-cp → VM 101 scsi0 (100 GiB) | SMART overall passed; 30 °C at collection. |
| sff | sdc | PNY CS900 1TB SSD | 1000.2 | pve / hp-prodesk-vmstore → VM 100 scsi0 + scsi1 | SMART overall passed; 33 °C at collection. |
| elite | nvme0n1 | INTEL SSDPEKNW512G8 | 512.1 | hp-elite-vmstore → VM 100 scsi1 (440 GiB); LXC 101 rootfs (10 GiB) | SMART overall passed; 35 °C at collection. NVMe endurance used: 76%; media errors: 0. |
| elite | nvme1n1 | WDC PC SN530 SDBPMPZ-256G-1101 | 256.1 | pve / local-lvm → VM 100 scsi0 (128 GiB) | SMART overall passed; 44 °C at collection. NVMe endurance used: 3%; media errors: 0. |
| gpu | sda | PNY CS900 1TB SSD | 1000.2 | pve / tr-sda-vmstore → VM 100 scsi4 (800 GiB) | SMART overall passed; 33 °C at collection. |
| gpu | sdb | MK000480GWCEV | 480.1 | md0 → ssd-ent → VM 100 scsi3 (440 GiB) | SMART overall passed; 18 °C at collection. |
| gpu | sdc | MK000480GWCEV | 480.1 | md0 → ssd-ent → VM 100 scsi3 (440 GiB) | SMART overall passed; 24 °C at collection. |
| gpu | nvme0n1 | EDILOCA EN605 512GB | 512.1 | nvme0-vmstore → VM 100 scsi0 (16 GiB) + scsi1 (434 GiB) | SMART overall passed; 54 °C at collection. NVMe endurance used: 16%; media errors: 0. |
| gpu | nvme1n1 | EDILOCA EN605 512GB | 512.1 | nvme1-vmstore → VM 100 scsi2 (450 GiB) | SMART overall passed; 54 °C at collection. NVMe endurance used: 20%; media errors: 0. |
| dell | sdb | R9M2SH6Q240GQF72C | 240.1 | pve / local-lvm → VM 100 scsi0 (128 GiB) | SMART overall passed; 31 °C at collection. |
| dell | sdc | APPLE SSD SM0256G | 251.0 | dell-apple-vmstore → VM 100 scsi2 (220 GiB) | SMART overall passed; 29 °C at collection. |
| shed | sda | PNY CS900 1TB SSD | 1000.2 | hp-ssd-vmstore → VM 100 scsi1 (850 GiB) | SMART overall passed; 33 °C at collection. |
| shed | nvme0n1 | SK hynix BC501 HFM256GDJTNG-8310A | 256.1 | pve / local-lvm → VM 100 scsi0 (128 GiB) | SMART overall passed; 41 °C at collection. NVMe endurance used: 6%; media errors: 0. |
| pi | nvme0n1 | Patriot M.2 P300 256GB | 256.1 | Ubuntu root; Docker services | SMART overall passed; 32 °C at collection. NVMe endurance used: 13%; media errors: 0. |
| nas | sda | HP SSD S700 500GB | 500.1 | ai-pool | SMART overall passed; 44 °C at collection. Lifetime CRC counter: 816; this alone does not prove current errors. |
| nas | sdb | Samsung SSD 860 EVO 1TB | 1000.2 | ai-pool | SMART overall passed; 32 °C at collection. Lifetime CRC counter: 4; this alone does not prove current errors. |
| nas | sdc | HUH721010AL4200 | 10000.8 | BigTank mirror-0 | SMART overall passed; 37 °C at collection. |
| nas | sdd | HUH721010AL4200 | 10000.8 | BigTank mirror-1 | SMART overall passed; 50 °C at collection. |
| nas | sde | T-FORCE 512GB | 512.1 | boot-pool mirror | SMART overall passed; 33 °C at collection. |
| nas | sdf | HUH721010AL4200 | 10000.8 | BigTank mirror-0 | SMART overall passed; 45 °C at collection. |
| nas | sdg | P3-512 | 512.1 | ai-pool | SMART overall passed; 30 °C at collection. |
| nas | sdh | HUH721010AL4200 | 10000.8 | BigTank mirror-1 | SMART overall passed; 50 °C at collection. |
| nas | sdi | MK000480GWCEV | 480.1 | boot-pool mirror | SMART overall passed; 19 °C at collection. |
| nas | sdj | ST10000NM0096 | 10000.8 | Backup10T single disk | SMART overall passed; 32 °C at collection. |
| nas | sdk | Samsung SSD 850 EVO 500GB | 500.1 | No imported pool membership observed | SMART overall passed; 31 °C at collection. Lifetime CRC counter: 8162; this alone does not prove current errors. Samsung 850 EVO retired from Dell in PR #2946; SMART pass does not reverse the recorded load-test failure. |

## VM disk paths

These are declared Proxmox attachments. The Dell inactive backing store is an explicit exception to availability.

| Host / VM | Slot | Backing | Size |
|---|---|---|---|
| sff / 100 | scsi0 | `hp-prodesk-vmstore:vm-100-disk-0` | 128 GiB |
| sff / 100 | scsi1 | `hp-prodesk-vmstore:vm-100-disk-1` | 690 GiB |
| sff / 101 | scsi0 | `hp-sff-cp-vmstore:vm-101-disk-0` | 100 GiB |
| elite / 100 | scsi0 | `local-lvm:vm-100-disk-0` | 128 GiB |
| elite / 100 | scsi1 | `hp-elite-vmstore:vm-100-disk-0` | 440 GiB |
| gpu / 100 | scsi0 | `nvme0-vmstore:vm-100-disk-1` | 16 GiB |
| gpu / 100 | scsi1 | `nvme0-vmstore:vm-100-disk-2` | 434 GiB |
| gpu / 100 | scsi2 | `nvme1-vmstore:vm-100-disk-0` | 450 GiB |
| gpu / 100 | scsi3 | `ssd-ent:vm-100-disk-0` | 440 GiB |
| gpu / 100 | scsi4 | `tr-sda-vmstore:vm-100-disk-0` | 800 GiB |
| gpu / 102 | scsi0 | `truenas-smb:102/vm-102-disk-0.raw` | 305 GiB |
| dell / 100 | scsi0 | `local-lvm:vm-100-disk-0` | 128 GiB |
| dell / 100 | scsi1 | `dell-ssd-vmstore:vm-100-disk-0` | 400 GiB |
| dell / 100 | scsi2 | `dell-apple-vmstore:vm-100-disk-0` | 220 GiB |
| shed / 100 | scsi0 | `local-lvm:vm-100-disk-0` | 128 GiB |
| shed / 100 | scsi1 | `hp-ssd-vmstore:vm-100-disk-0` | 850 GiB |

## Proxmox storage

For thick LVM, allocated capacity is not guest filesystem usage. Thin-pool usage and NAS share capacity use different accounting.

| Host | Store | Type | Status | Total GiB | Used / allocated GiB | Available GiB |
|---|---|---|---|---:|---:|---:|
| sff | hp-prodesk-vmstore | lvm | active | 930.0 | 922.0 | 8.0 |
| sff | hp-sff-cp-vmstore | lvm | active | 372.6 | 100.0 | 272.6 |
| sff | local | dir | active | 93.9 | 13.1 | 76.0 |
| elite | hp-elite-vmstore | lvm | active | 476.9 | 450.0 | 26.9 |
| elite | local | dir | active | 67.7 | 12.7 | 51.5 |
| elite | local-lvm | lvmthin | active | 141.2 | 59.7 | 81.6 |
| gpu | local | dir | active | 93.9 | 40.9 | 48.4 |
| gpu | nvme0-vmstore | lvmthin | active | 467.3 | 230.4 | 236.9 |
| gpu | nvme1-vmstore | lvmthin | active | 467.3 | 29.0 | 438.3 |
| gpu | ssd-ent | lvm | active | 447.0 | 440.0 | 7.0 |
| gpu | tr-sda-vmstore | lvm | active | 930.5 | 904.0 | 26.5 |
| gpu | truenas-smb | cifs | active | 8468.1 | 508.2 | 7959.9 |
| dell | dell-apple-vmstore | lvm | active | 233.8 | 220.0 | 13.8 |
| dell | dell-ssd-vmstore | lvm | inactive | 0.0 | 0.0 | 0.0 |
| dell | local | dir | active | 66.6 | 15.4 | 47.8 |
| dell | local-lvm | lvmthin | active | 140.0 | 92.2 | 47.8 |
| shed | hp-ssd-vmstore | lvm | active | 931.5 | 850.0 | 81.5 |
| shed | local | dir | active | 67.7 | 13.7 | 50.6 |
| shed | local-lvm | lvmthin | active | 153.2 | 14.4 | 138.8 |

## Longhorn disks

Scheduled bytes are requested replica capacity, not bytes used. They can exceed filesystem capacity under configured overprovisioning.
Dell values below are controller observations despite the missing physical backing store.

| Node | Disk | Scheduling | Capacity GiB | Free GiB | Scheduled GiB |
|---|---|---|---:|---:|---:|
| `talos-prod-cluster-v2-dell-workers-2jfrb8` | dell-apple | True | 219.9 | 212.0 | 0.0 |
| `talos-prod-cluster-v2-dell-workers-2jfrb8` | dell-ssd | True | 399.8 | 392.1 | 0.0 |
| `talos-prod-cluster-v2-dell-workers-2jfrb8` | talos-ephemeral | False | 125.8 | 69.4 | 0.0 |
| `talos-prod-cluster-v2-gpu-workers-jxfkdr` | gpu-bulk | True | 799.6 | 750.3 | 530.1 |
| `talos-prod-cluster-v2-gpu-workers-jxfkdr` | ssd-flash | True | 439.9 | 298.2 | 482.0 |
| `talos-prod-cluster-v2-gpu-workers-jxfkdr` | talos-ephemeral | False | 433.8 | 235.9 | 0.0 |
| `talos-prod-cluster-v2-hp-elite-workers-l5zlgr` | hp-elite-nvme | True | 439.8 | 421.4 | 121.0 |
| `talos-prod-cluster-v2-hp-elite-workers-l5zlgr` | talos-ephemeral | False | 125.8 | 74.3 | 0.0 |
| `talos-prod-cluster-v2-hp-micro-workers-pstbbd` | hp-micro-ssd | False | 849.6 | 833.2 | 0.0 |
| `talos-prod-cluster-v2-hp-micro-workers-pstbbd` | talos-ephemeral | False | 125.8 | 109.9 | 0.0 |
| `talos-prod-cluster-v2-hp-sff-workers-h76ncc` | hp-sff-ssd | True | 689.7 | 572.2 | 376.0 |
| `talos-prod-cluster-v2-hp-sff-workers-h76ncc` | talos-ephemeral | False | 125.8 | 82.3 | 0.0 |

## TrueNAS and management services

| Pool | Size | Allocated | Layout |
|---|---:|---:|---|
| Backup10T | 9.08 TiB | 68% | One 10 TB disk |
| BigTank | 18.16 TiB | 56% | Two mirrors · four 10 TB disks |
| ai-pool | 1.82 TiB | 76% | Three SSDs striped |
| boot-pool | 0.22 TiB | 25% | T-FORCE + HPE mirror |

`ai-pool` and `Backup10T` have no member-disk redundancy. Pool state does not prove backup freshness.
The NAS exposed eight enabled NFS shares. The dataset inventory contains 203 datasets and zvols.
ARC held 83.3 GiB at collection; cache size varies with workload and uptime.
Share definitions and dataset usage were inspected without reading application files.

| Host | Service | Version / image | Observed state |
|---|---|---|---|
| pi | proxcenter-frontend | `ghcr.io/adminsyspro/proxcenter-frontend:1.4.10-arm64-20261001` | Up 13 days (healthy) |
| pi | proxcenter-postgres | `postgres:16.15-alpine3.24` | Up 13 days (healthy) |
| pi | omni | `ghcr.io/siderolabs/omni:v1.12.3` | Up 13 days |
| pi | technitium-dns | `technitium/dns-server:15.5.1` | Up 13 days |
| pi | omni-infra-provider-proxmox-hp-micro | `ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0` | Up 13 days |
| pi | omni-infra-provider-proxmox-hp-elite | `ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0` | Up 13 days |
| pi | omni-infra-provider-proxmox-hp-sff | `ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0` | Up 13 days |
| pi | omni-infra-provider-proxmox-dell | `ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0` | Up 13 days |
| pi | omni-infra-provider-proxmox-threadripper | `ghcr.io/siderolabs/omni-infra-provider-proxmox:v0.3.0` | Up 13 days |
| nas | tailscale | `1.4.16` | RUNNING |
| nas | rustfs | `1.1.31` | RUNNING |
| nas | physical-monitoring | `1.0.0` | RUNNING |

## Evidence and refresh method

- [Sanitized complete inventory](../assets/inventory/2026-10-15/inventory.json): hosts, VM allocations, passthrough mappings, services, pool accounting and claims.
- [NAS datasets CSV](../assets/inventory/2026-10-15/nas-datasets.csv): 203 datasets/zvols with ZFS usage; eight enabled NFS shares are in the inventory JSON.
- [Physical disks CSV](../assets/inventory/2026-10-15/physical-disks.csv) and [PVC CSV](../assets/inventory/2026-10-15/claims.csv).
- [Talos disk, volume and mount observations](../assets/inventory/2026-10-15/talos-storage.json).
- [Longhorn disk accounting and conditions](../assets/inventory/2026-10-15/longhorn-disks.json).

Host evidence: `lsblk`, `lscpu`, `/proc/meminfo`, `pveversion`, `qm list`, filtered `qm config`, `pct list`, `pvesm status`, LVM reports and `smartctl -a`.
NAS evidence: `zpool status`, `zpool list`, `zfs list`, ARC counters, and read-only middleware queries for VMs, apps, shares and replication.
Cluster evidence: Kubernetes node, pod, PVC, PV, Argo CD and Longhorn APIs; Talos `disks`, `discoveredvolumes` and `mountstatus` resources.

Use the [README service-account access procedure](https://github.com/mitchross/talos-argocd-proxmox#3-authenticate-and-get-cluster-access) before Talos queries.
Use the [Proxmox storage reference](https://pve.proxmox.com/pve-docs/pvesm.1.html) for storage accounting and commands.
Raw responses remain private under `/tmp/talos-inventory-20261015`; published files omit credentials, disk serials and raw middleware configurations.

Historical benchmarks remain dated September 20 and October 11. They were not rerun or relabelled as current measurements.
