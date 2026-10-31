# Come have a look around the lab

The HPs do the everyday work. The Threadripper has two RTX 3090s. The shed talks to
radios over a Wi-Fi bridge. TrueNAS holds the big files and backups, and a Pi
runs Omni and DNS. Click a machine to see what is inside it, or explore the
private, public and shed network paths below.

**[October 15 full inventory](inventory/2026-10-15-full-inventory.md)** covers all
seven hosts, VM allocations, physical disks, Talos mounts and storage accounting.
The explorer below uses that refreshed snapshot. Performance measurements retain
their September 20 and October 11 dates.

The explorer has not been refreshed since then: it still shows the retired Dell OptiPlex
and not the two bare-metal minis. For the current machine list and load, read the
**[October 27 fleet inventory](inventory/2026-10-27-fleet-inventory.md)**. For disks, read
the [disk map](domains/storage/disk-map.md).

<div id="lab-explorer">
  <p>The interactive inventory is loading. The <a href="../inventory/2026-10-15-full-inventory/">full written inventory</a> is also available.</p>
</div>

## Findings — October 15

- Dell’s `dell-ssd-vmstore` was inactive and its physical T-FORCE drive was absent.
  Talos still reported the mount. These observations do not establish successful disk I/O.
- SFF’s control plane uses the Intel S3610. Its spare PNY SSD has no volume group.
- The GPU host has two RTX 3090s and separate system, model-cache, enterprise and bulk-storage paths.
- All four NAS pools reported ONLINE. The local replication task still had no schedule and a May 2025 completion.

The [full inventory](inventory/2026-10-15-full-inventory.md) records the evidence
and limits. Historical performance results remain in the
[fleet assessment](inventory/2026-09-20-capacity-and-benchmarks.md) and
[etcd measurements](inventory/2026-10-11-etcd-on-s3610.md).

## What this page knows

The hardware, VM, node, pod placement and claim inventory was collected on
**October 15, 2026**, through read-only SSH, Kubernetes and Talos APIs.
This is not a live monitoring screen. Queries ran separately, so the data is
not an atomic snapshot. Network diagrams retain their documented design;
router, bridge, DNS and HTTP paths were not tested.

The “what if” view explains dependencies. It does not switch machines off
or prove recovery time. Historical benchmarks retain their own dates and paths.

Physical-drive sizes use decimal GB/TB. VM disks and RAM use GiB/MiB. Disk bars
compare capacity within a host; they do not claim to show used space. NAS pool
bars show the recorded ZFS pool allocation, which differs from the dashboard's
usable-dataset accounting. Device names identify the inspected layout and can
change after reconnecting hardware.

The complete sanitized page inventory is downloadable inside the explorer.
Its source is [`lab-inventory-data.js`](assets/lab-inventory-data.js); it contains
no disk serial numbers, credentials or raw diagnostic dumps. Update that snapshot
and its date together after hardware moves; `runtimeVersionsCheckedAt` records
the separate node-version check. Keep measured state separate from
suggestions, and check the page at desktop and phone widths before publishing.
