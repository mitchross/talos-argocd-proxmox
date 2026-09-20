# Come have a look around the lab

The HPs do the everyday work. The Threadripper has two RTX 3090s. The shed talks to
radios over a Wi-Fi bridge. TrueNAS holds the big files and backups, and a Pi
runs Omni and DNS. Click a machine to see what is inside it, or explore the
private, public and shed network paths below.

**Start with the [September 20 capacity verdicts](inventory/2026-09-20-capacity-and-benchmarks.md)**
for current Proxmox disk speeds, Kubernetes storage paths, RAM headroom and
consolidation limits. Select a machine below for its dated inventory and latest
measurement summary. The [NAS reference](nas-performance.md) separates physical
disk reads, RAM cache and flushed writes.

<div id="lab-explorer">
  <p>The interactive inventory is loading. The <a href="../audits/2026-09-05-inventory/">full written inventory</a> is also available.</p>
</div>

## Current priorities — September 20

1. **Protect data before removing a host.** 84 of 89 Longhorn volumes have one
   replica; the GPU host holds 44 sole copies. SFF still hosts the only control plane.
2. **Investigate SFF contention before choosing a replacement.** Its root/worker
   disk had slow bulk writes, and both guests showed CPU steal. The control-plane
   disk is separate; its etcd history is the relevant evidence for that path.
3. **Plan Dell retirement as a migration, not a power-off.** Its applications are
   the best consolidation candidate, but data, replica protection and placement
   constraints must be resolved first. Keep device-bound Elite and Shed roles distinct.
4. **Keep NAS RAM and check cooling.** The cache is useful; smaller replacement
   capacities remain unvalidated. BigTank HDDs at 54–58°C justify airflow checks.

These recommendations replace the September 5 purchase ordering. The
[latest report](audits/2026-09-20-homelab-report.html) explains the priorities;
the [fleet assessment](inventory/2026-09-20-capacity-and-benchmarks.md) owns current
host and guest benchmarks. The [recovery guide](disaster-recovery.md) owns
operational recovery procedures.

## What this page knows

The hardware inventory is the **September 5, 2026 audit snapshot**, with a
separately dated **September 20 NAS, Proxmox and Kubernetes performance updates**. This
is not a live monitoring screen.
Host hardware and disks came from read-only SSH inspection. Node IPs and software
versions were checked again at **2026-09-06 01:48 UTC** after the
[Talos and Kubernetes upgrade](audits/2026-09-05-upgrade-and-disks.md).
Pod placement and claims still use the earlier audit snapshot, which includes
applications subsequently retired. The
"what if" view explains dependencies; it does not switch machines off or prove
a measured recovery time.

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
