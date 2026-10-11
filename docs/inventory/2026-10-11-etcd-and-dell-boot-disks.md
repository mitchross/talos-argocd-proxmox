# etcd and Dell boot disks — October 11, 2026

**What this is:** measurements for two drive changes: the etcd disk on the HP SFF
and the Proxmox boot disk on the Dell. The current layout is in the
[disk map](../domains/storage/disk-map.md); this page keeps the numbers behind it.
Raw data: `docs/assets/fleet-benchmarks/2026-10-11/`.

## etcd on the Intel DC S3610

The control-plane VM disk moved from a consumer PNY CS900 to an Intel DC S3610
400 GB (enterprise SATA, power-loss protection) with an online `pvmove`.
Same VM, same etcd member, same workload.

etcd's own latency histograms (Prometheus, 6-hour windows, Oct 1–11):

| Metric | PNY CS900 | Intel S3610 | Change |
|---|---:|---:|---|
| WAL fsync p50 | 1.66 ms | 0.56 ms | 3× faster |
| WAL fsync p99 | about 7.0 ms | 3.8–4.4 ms | about 1.8× faster |
| Backend commit p50 | 3.05 ms | 0.61 ms | 5× faster |
| Backend commit p99 | about 7.6 ms | 3.8–5.1 ms | about 1.7× faster |
| Mean physical write wait (host, 30 s sample) | 2.02 ms | 0.08 ms | — |

etcd's guidance is WAL p99 below 10 ms and backend commit p99 below 25 ms. Both
were already met; the S3610 adds headroom for load spikes. The p99 rose slightly
over the last day. etcd's database file is 412 MB with about 15% live data, so
defragment it in a quiet window before blaming the disk.

## Dell boot disk: Cisco SSD-240G

The Proxmox root, swap and the Dell worker's Talos system disk moved from an
Apple SM0256G on a PCIe adapter to a Cisco SSD-240G (M.2 SATA, onboard port,
6 Gb/s). The move used `pvmove` for root and swap and `qm disk move` for the VM
disk; the worker was down for about 5 minutes.

Host-root benchmark (same script as 2026-09-20,
`docs/assets/fleet-benchmarks/2026-09-20/proxmox-benchmark.py`, 1 GiB file in `/var/lib/vz`):

| Test | Apple SM0256G (2026-09-20) | Cisco SSD-240G (2026-10-11) |
|---|---:|---:|
| Sequential write, fsync every 64 MiB | 636 MB/s | 146 MB/s |
| Sequential read | 1,926 MB/s | 416 MB/s |
| 8 KiB write + fsync, p50 / p99 | 7.2 / 10.8 ms | 9.2 / 13.1 ms |

The Cisco drive is slower than the Apple drive. The Apple drive used a PCIe
link; the Cisco uses SATA. For a Proxmox root and a Talos system disk this does
not limit the worker: the Talos `/var` holds images, logs and `emptyDir`, and
Longhorn data sits on the Samsung 850 EVO. SMART: passed, 24 power-on hours,
0 reallocated sectors. It reports no power-loss protection.

The VM disk copy wrote every block, so the thin pool showed 91% used. One
`fstrim` of the Talos `/var` returned it to 47%. Talos trims every node volume
weekly by itself (see [disk writes](../domains/storage/disk-writes.md)).
