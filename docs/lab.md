# Come have a look around the lab

The HPs do the everyday work. The Threadripper has the 3090. The shed talks to
radios over a Wi-Fi bridge. TrueNAS holds the big files and backups, and a Pi
runs Omni and DNS. Click a machine to see what is inside it, or explore the
private, public and shed network paths below.

<div id="lab-explorer">
  <p>The interactive inventory is loading. The <a href="../audits/2026-09-05-inventory/">full written inventory</a> is also available.</p>
</div>

## What I would change first

1. **Give the control plane a better disk.** The SFF has plenty of capacity;
   the measured problem is how long durable writes take.
2. **Make the two HPs the everyday pair.** Protect selected app data on both
   machines. Keep the Dell useful without depending on it long term.
3. **Let the Threadripper be the heavy-work machine.** Keep its enterprise
   mirror and GPU. Gradually remove ordinary services' dependence on that host.
4. **Keep the NAS RAM.** Its cache is doing useful work. We have not shown
   that reducing it would be worth the trade-off.

Argo's directory layout is worth keeping. The work is in disk placement,
recovery, a few broad diff exceptions, and clearer rules about which jobs run
where. It does not call for a new GitOps platform.

The [full review](audits/2026-09-05-hardware-and-placement-review.md) has the
reasoning and proposed PRs. The [inventory](audits/2026-09-05-inventory.md) links
the application, route, volume and documentation CSVs. The
[recovery guide](disaster-recovery.md) owns the actual procedures.

## What this page knows

This is the **September 5, 2026 audit snapshot**, not a live monitoring screen.
Host hardware and disks came from read-only SSH inspection; node IPs were checked
again while this page was prepared. Pod placement and claims use the earlier
audit snapshot, which includes applications subsequently retired. The
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
and its date together after hardware moves. Keep measured state separate from
suggestions, and check the page at desktop and phone widths before publishing.
