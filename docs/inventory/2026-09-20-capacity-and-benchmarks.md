# Fleet capacity and storage measurements — September 20

**The lab has spare compute, but that does not yet make it safe to remove a
machine.** Memory placement, single-copy data, hardware-bound apps and the sole
control plane matter more than adding CPU. The Elite has the least host-memory
headroom; the SFF worker/root SSD had the slowest flushed sequential write in
this sample. Neither observation alone proves failing hardware.

**Status:** measured September 20, 2026. Proxmox host probes, Kubernetes volume
probes and NAS pool probes are separate measurements. Recommendations below are
proposals; no host migrations, resource changes or storage reconfiguration were
performed.

This answers three different questions:

| Measurement | What it tells us | What it does not tell us |
|---|---|---|
| Proxmox root filesystem | Host OS disk behavior, physical RAM and guest allocations | Speed of a different disk holding the VM data |
| Kubernetes mounted volume | Application-visible behavior through that volume's actual path | Every disk in a host, or maximum simultaneous application users |
| [NAS pools and RAM cache](../nas-performance.md) | Disk-backed versus cached reads and flushed writes | End-to-end SMB/NFS speed unless explicitly measured through that path |

## Physical hosts: current allocations and headroom

Host CPU use below is a **15-second sample before the host benchmarks**, not a
peak-demand or capacity guarantee. RAM uses GiB. “Available” is Linux's estimate
of reclaimable host memory; it is not the unused portion of a guest's allocation.

| Host | CPU threads / active guest vCPUs | Usable RAM | Active guest RAM assigned | Host available RAM | CPU busy / I/O wait |
|---|---:|---:|---:|---:|---:|
| Threadripper `.14` | 32 / 30 | 125.7 | 100 | 18.3 | 33.8% / 0.2% |
| Dell `.16` | 6 / 6 | 39.0 | 30 | 7.4 | 41.4% / 1.1% |
| Shed Micro `.20` | 6 / 4 | 31.1 | 12 | 25.0 | 4.7% / 0.2% |
| HP SFF `.21` | 6 / 10 | 62.6 | 52 | 8.1 | 39.3% / 0.9% |
| HP Elite `.22` | 20 / 18 | 30.6 | 26 | 4.0 | 22.5% / 0.2% |

SFF's 52 GiB comprises a 40 GiB worker VM and a 12 GiB control-plane VM. Its ten
assigned vCPUs share six host threads; allocation oversubscription is not itself
evidence of saturation. The Elite's 26 GiB comprises a 24 GiB worker and a 2 GiB
Proxmox Datacenter Manager container. The stopped Kali VM on Threadripper is
excluded from active allocations.

The Shed VM has 12 GiB assigned but had touched much less memory when inspected,
about an hour after host boot. Its 25 GiB host-available reading should not be
treated as 25 GiB of permanently uncommitted capacity. The active Talos VMs have
ballooning disabled. Hypervisor overhead also needs room: Proxmox documents host
memory requirements in addition to guest allocations.
[Proxmox hardware requirements](https://www.proxmox.com/en/products/proxmox-virtual-environment/requirements).

## Proxmox root-disk speeds

Each host received a new temporary 1 GiB file on `/var/lib/vz`, backed by its root
ext4 filesystem. The write called `fsync` every 64 MiB and at completion; the read
used per-file cache-eviction hints after flushing. Physical disk counters recorded
approximately 1 GiB read from the corresponding disk on every host. Hints alone
would not prove the data came from disk.

The last columns time **128 separate 8 KiB random writes, each followed by
`fsync`**. The p99 is the sampled 99th-percentile cutoff, not a guaranteed upper
bound. MB/s uses decimal megabytes. These short runs include live background
work and do not exhaust every SSD's internal write cache.

**Verdicts are practical assessments of this measured workload, not industry
percentiles.** Manufacturer numbers below are advertised sequential peaks, not
matched averages or expected `fsync` latency. Vendor queue depth, filesystem,
flush policy and cache state differ from these tests. R/W means read/write MB/s.

| Host and tested root disk | Flushed write MB/s | Disk-backed read MB/s | 8 KiB write + fsync p50 / p99 | Verdict / reference |
|---|---:|---:|---:|---|
| Threadripper: PNY CS900 `sda` | 359.7 | 406.5 | 1.990 / 2.313 ms | **Normal SATA-class bulk; good small-write tail.** [PNY 1 TB peak: 535 R / 515 W][pny-cs900]; our flushed, live-host test is different. |
| Dell: Apple SM0256G `sdb` | 635.7 | 1,926.3 | 7.177 / 10.834 ms | **Fast reads, slow small-write tail within this fleet.** Other root paths had 0.91–8.46 ms p99. No matched official OEM throughput baseline verified. |
| Shed Micro: SK hynix BC501 `nvme0n1` | 638.6 | 1,159.8 | 1.013 / 1.175 ms | **Fast burst throughput and small writes within this fleet.** No matched official OEM baseline verified; this does not establish indefinite write speed. |
| SFF: PNY CS900 `sdb` | 83.1 | 401.3 | 2.381 / 8.464 ms | **Slow bulk writes; investigate.** Other PNY host: 359.7 MB/s write; [vendor peak: 535 R / 515 W][pny-cs900]. Similar read speed does not explain the write gap. |
| Elite: WDC SN530 `nvme1n1` | 638.2 | 888.7 | 0.607 / 0.910 ms | **Fast root responsiveness; below vendor sequential peaks.** [256 GB SN530: 2,400 R / 950 W][wd-sn530]. This is the root SSD, not the Intel VM tier. |

[pny-cs900]: https://www.pny.com/ssd-cs900?iscommercial=true
[wd-sn530]: https://documents.sandisk.com/content/dam/asset-library/en_us/assets/public/western-digital/product/internal-drives/pc-sn530-ssd/product-brief-sn530-ssd.pdf

**SFF's root/worker physical disk is the clearest sequential-write investigation
target in this sample.** It read at roughly the same rate as Threadripper's PNY,
but its flushed write was much slower. The cause was not isolated: controller
behavior, drive state and concurrent worker traffic differ. The separate SFF
control-plane SSD was not tested by the host-root probe. Do not transfer this
result to etcd or conclude that either SSD is faulty.

**Dell's high sequential read speed does not imply fast durable small writes.**
Its small-write p99 was the highest in this host-root comparison. Conversely,
Elite's fast root-disk result says nothing about its separate Intel VM SSD.

| Host | Actual VM data tier excluded from the root probe |
|---|---|
| Threadripper | Enterprise SATA mirror and both EDILOCA NVMe tiers |
| Dell | Samsung 850 EVO data SSD |
| Shed Micro | PNY data SSD |
| SFF | Separate `sda` control-plane SSD; worker volumes share tested physical `sdb` but have another I/O path |
| Elite | Intel SSDPEKNW512G8 data SSD |

All tested root drives passed their reported SMART status before and after the
probe. All five temporary directories were removed and their absence checked.
The Elite **VM data SSD** reported 75% endurance used, no NVMe media errors and
no critical warning. Dell's **VM data SSD** retained 8,162 lifetime CRC errors;
the count did not increase across these checks. Neither is a failure probability.

## Kubernetes volume measurements

The completed comparison used a **512 MiB new scratch file**, one process and
queue depth one, with 1 MiB direct-I/O sequential writes/reads. Writes included a
final `fsync`; 128 separate buffered 8 KiB random writes each included `fsync`.
Direct reads bypass the guest/client page cache, but upstream caches may still
serve them. Each row records the mounted volume and its actual replica location.

These are **complete application storage paths**, so bare-drive specifications
are only context. A controlled industry average for this exact VM, Longhorn,
network and durability combination was not established. “Normal for light state”
is a workload-fit assessment, not a database certification. An 8 KiB synthetic
`fsync` p99 is not interchangeable with etcd's own WAL latency metric.

| Application volume and path | Replica / backend | Write MB/s | Read MB/s | 8 KiB write + fsync p99 | Verdict / reference |
|---|---|---:|---:|---:|---|
| Immich ML cache, `/cache` | 1 × Elite Intel NVMe tier | 157.5 | 240.0 | 1.29 ms | **Fastest tested local one-copy app path; good for light state in this sample.** [Bare 512 GB Intel 660p peak: 1,500 R / 1,000 W][intel-660p]; not a matched Longhorn baseline. |
| Open-Meteo data, `/app/data` | 1 × SFF PNY worker tier | 58.3 | 138.0 | 3.47 ms | **Normal for light state; modest bulk throughput.** [Bare PNY peak: 535 R / 515 W][pny-cs900]; extra VM/storage layers make this a different test. |
| Paperless data, `/usr/src/paperless/data` | 1 × GPU default Longhorn path on EDILOCA NVMe | 56.1 | 123.0 | 7.09 ms | **Slow bulk versus Elite; higher small-write tail than SFF.** Compare the one-copy rows, not an unverified EDILOCA vendor figure. No matched industry baseline. |
| SurfSense object store, `/app/.local_object_store` | 2 copies: Dell Samsung + SFF PNY | 37.1 | 102.4 | 9.42 ms | **Slow bulk in this comparison; moderate small-write tail.** Both replicas are in the measured path. No matched two-copy baseline; replication cost was not isolated. |
| Intercept data, `/app/data/weather_sat` | App on Shed; its running copy is on SFF, across the Wi-Fi path | 18.8 | 22.0 | 39.70 ms | **Slow for interactive writes.** Wired consumer-tier app paths measured 1.29–9.42 ms p99; the Wi-Fi/SFF path differs and local Shed SSD speed does not predict it. |
| Radar state, `/data/state` | 1 × GPU HPE enterprise mirror, `/var/mnt/longhorn-ssd-flash` | 33.9 | 95.4 | 46.78 ms | **Slow in this loaded test; retest before judging hardware.** About 8.1 GB of concurrent disk reads confound comparison. No matched idle mirror/Longhorn baseline. |
| TubeSync downloads, `/downloads` | NAS `BigTank/k8s/tubearchivist`, `sync=disabled` | 135.5 | 174.9 | 3.50 ms, **not a durability guarantee** | **Useful bulk throughput; exclude from durable-write rankings.** About 1.40 Gbit/s payload read; no matched SMB industry baseline. Server write policy prevents a like-for-like `fsync` comparison. |

[intel-660p]: https://www.solidigm.com/content/dam/solidigm/en/site/products/client/d6/660p/documents/ssd-660p-series-512gb-m-2-80mm-pcie-3-0-x4-3d2-qlc-spec-sheet.pdf

**The Shed's slow result is a remote-storage path, not a benchmark of its local
SSD.** The same SFF storage tier is reached through a different client and link.
This is a practical reason to keep radio workloads selective and avoid treating
spare Shed RAM as ordinary wired compute capacity.

The HPE mirror measurement ran during substantial unrelated I/O: the guest data
disk recorded about **8.1 GB of reads** while the benchmark file was only 0.54 GB.
That result identifies the observed application path under load; it does not
establish that enterprise SSD hardware is slower than the consumer NVMe. Repeat
under controlled comparable activity before making that purchase conclusion.

Paperless's default `/var/lib/longhorn` path maps through the GPU VM's 434 GiB
`scsi1` data disk on `nvme0-vmstore` (EDILOCA). It is neither the 16 GiB VM boot
disk nor the Proxmox host's PNY root SSD. The separate enterprise tier maps
through the 300 GiB `scsi3` disk. These distinctions explain why a label such as
“Threadripper disk speed” would be insufficient.

The SMB dataset inherited **`sync=disabled`** from `BigTank/k8s`; compression was
`zstd` and record size 128 KiB. Calling `fsync` at the client cannot establish
power-loss durability when the server's dataset ignores synchronous-write
requests. Its latency must not be ranked as equivalent to the other rows' save
behavior. This is an existing setting, unchanged by the benchmark.

The host-root tests used a different file size and buffered/periodic-flush
method; NAS-local tests used 4 GiB and other cache modes. **Do not subtract these
tables to calculate Longhorn overhead.** A valid overhead comparison would hold
the physical tier, client, I/O method, durability and background activity constant.

### The first attempt caused a container restart

The initial 1 GiB buffered-write attempt in Copyparty hit its **1 GiB container
memory limit** and was OOM-killed at **17:54:04 UTC**. It restarted automatically
and returned to Ready. The incomplete 996,671,488-byte scratch file and its exact
temporary directory were removed and absence verified at 17:56 UTC. Benchmark
writes used newly created scratch files.

The test was stopped and changed to smaller direct sequential I/O to avoid the
same dirty-page burst. All seven subsequent probes completed and removed their
scratch files. Independent [postflight checks](../assets/fleet-benchmarks/2026-09-20/kubernetes-postflight.json)
confirmed all eight checked scratch locations empty, every tested container Ready,
and all six nodes Ready. The first attempt is retained as incident evidence and
is not mixed into the comparison table. Spare memory on the host does not override a
container's memory limit.

## Application demand and placement

The history ends **September 20 at 17:40 UTC, before these benchmarks**. It covers
seven days, sampling five-minute rates every ten minutes. The p95 and maximum
describe those sampled windows, so short spikes can be missed. Shed coverage is
roughly half the window. Memory is guest total minus available, including its OS
and unreclaimable allocations; it is not just application RSS.

| Talos node | Guest memory p95 / sampled max GiB | Current requested / allocatable GiB | CPU nonidle p95, cores |
|---|---:|---:|---:|
| Control plane on SFF | 5.91 / 6.16 | 3.77 / 11.07 | 0.95 |
| Dell worker | 12.00 / 12.50 | 14.24 / 28.89 | 1.87 |
| GPU worker | 51.37 / 53.19 | 70.75 / 97.67 | 9.06 |
| Elite worker | 11.17 / 14.14 | 18.26 / 22.98 | 3.36 |
| Shed worker | 2.32 / 2.33 | 2.57 / 11.19 | 0.24 |
| SFF worker | 13.39 / 14.17 | 12.93 / 38.68 | 2.13 |

CPU nonidle excludes I/O wait but includes **steal**, time the guest wanted CPU
but the hypervisor did not supply it. SFF worker steal p95 was **9.66% of its six
vCPUs**, and the control plane's was **6.9% of four vCPUs**. GPU, Dell and Elite
were about 0.76%, 1.1% and 0.11%. This supports investigating contention on SFF
despite the fleet's spare aggregate CPU. It does not establish a CPU upgrade as
the only remedy.

The pretest etcd history also remains relevant: WAL fsync p99 exceeded 10 ms in
about **9.14% of sampled windows**; backend commit p99 exceeded 25 ms in about
**0.99%**. The 95th percentile across those per-window p99 values was 12.07 ms
for WAL and 15.87 ms for backend commits, with sampled maxima 31.16 and 55.71 ms.
These are historical application-storage measurements, not results from the
different root SSD tested above. Recheck the control-plane path and CPU
contention together.

Four OOM counter events appeared on each of the GPU and Elite guests during
this pretest window. The counters do not identify whether container limits or
whole-guest pressure caused them; they are separate from the benchmark incident
described above. Low average usage does not remove application limit risks.

### Data and device dependencies

**84 of 89 Longhorn volumes had one configured replica.** Sole stored copies
were located on GPU (44), SFF (21), Elite (17) and Dell (2). The five two-copy
volumes all used Dell plus SFF. Healthy in this configuration means the requested
copies exist, not that each volume survives a host failure.

| Physical host lost | Non-DaemonSet pods displaced | Fit elsewhere in the optimistic request model | Additional blockers |
|---|---:|---:|---|
| Dell | 32 | 32 | Two sole volume copies; retain the other five volumes' two-host protection |
| GPU | 73 | 47 | 26 hard-pinned pods: 19 PostHog, 6 radar, 1 dual-GPU vLLM; 44 sole volume copies |
| Elite | 47 | 44 | Frigate Coral, Home Assistant Zigbee and Immich iGPU; 17 sole volume copies |
| Shed | 2 | 1 | SDR device dependency; its Intercept data copy is on SFF |
| SFF, including control plane | 56 | 46, hypothetically | Sole control-plane loss prevents rescheduling; 7 Coroot pods, including all 3 Keeper replicas, plus 3 control-plane-pinned cert-manager pods; 21 sole volume copies |

This is **not a scheduler simulation or a proven drain plan**. It considers
current requests, node selectors, required node affinity, taints and extended
devices, while retaining existing placements. It omits pod affinity/anti-affinity,
topology spread, host-port conflicts, priorities, volume access/availability and
migration overhead. SFF's result additionally assumes a functioning replacement
control plane that does not exist today.

## What can be consolidated?

**Dell is the best candidate to evaluate for eventual retirement, but it is not
ready to switch off.** An optimistic check using current pod requests could place
all 32 displaced non-DaemonSet pods elsewhere. It excludes several scheduler and
storage constraints, and Dell still holds two volumes' only copies plus copies
of five protected volumes. A real migration must move data and retain independent
copies before reducing the host count.

**Keep the SFF, Elite and GPU host as distinct roles for now.** GPU workloads
require the Threadripper's two 3090s; Elite carries hardware-dependent services;
SFF carries the sole control plane. Spare aggregate RAM cannot remove those
dependencies. The Shed's spare memory is behind a Wi-Fi link and its workloads
include physical radios; it is not interchangeable with a wired storage host.

The host view and Kubernetes view answer different consolidation questions:

- Moving entire VMs requires their configured memory, disk availability and
  compatible devices on the destination.
- Moving individual apps may use much less memory, but requires scheduler
  eligibility, recoverable data and working external devices.
- Neither a manager UI nor a Proxmox cluster creates those prerequisites.

Kubernetes places pods using requests, not instantaneous usage or the sum of
limits. A node with apparently low live memory use may still reject another pod
because its reserved capacity is used. Limits above node capacity also do not
promise every container can reach its limit simultaneously.
[Kubernetes resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

## Purchase priorities and practical workload fit

1. **Fix failure dependencies before buying more CPU.** Keep the Dell until data
   movement and a surviving-capacity plan are demonstrated. A single control
   plane on SFF still makes that physical host a scheduling failure boundary.
2. **Prioritize compatible wired-compute RAM if demand grows.** Elite has only
   about 4 GiB host-available memory and the most constrained worker reservation
   ratio. Rebalancing eligible apps may avoid an immediate purchase; record real
   peaks before increasing guest allocations.
3. **Investigate storage paths before replacing drives.** Recheck SFF under a
   comparable workload, measure the actual slow application path, and trend the
   Elite data SSD's endurance. Fast root NVMe does not repair a separate VM disk.
4. **Keep NAS memory while measuring its real working set.** The
   [NAS report](../nas-performance.md) demonstrates cache benefit and discusses
   cooling, durable random writes and redundant drive layouts. The measurements
   do not establish a minimum replacement RAM size.

For home services, web apps and background automation, free scheduling capacity
and storage tail latency are more actionable than a maximum sequential number.
Databases need consistent durable writes; large media and model files care more
about sequential throughput, cache and network limits. AI serving additionally
depends on GPU memory and inference concurrency. None of these disk probes
measures a supported user count or full application response-time target.

## Proxmox Datacenter Manager is already installed

This is an observed deployment, not a proposed pilot: **PDM 1.1.7** runs in
**LXC 101 on Elite**, at `https://192.168.10.151:8443`. Both API services were
active and its HTTPS page returned 200. The configuration lists all five Proxmox
hosts as remotes. Remote connection health and management actions were not tested.

ProxCenter remains a separate application on the Pi `.15`. Existing PDM means
the next decision is whether its current inventory and workflows meet the need,
not whether another manager must first be installed. PDM itself is lost when
Elite is unavailable; that is separate from the guests continuing to run on other
hosts. No clustering or manager configuration changed during this inspection.

## Evidence, limits and next verification

Download the [Proxmox summary](../assets/fleet-benchmarks/2026-09-20/proxmox-summary.json),
[exact host benchmark script](../assets/fleet-benchmarks/2026-09-20/proxmox-benchmark.py)
and [PDM status](../assets/fleet-benchmarks/2026-09-20/pdm-status.json).
The [pretest history](../assets/fleet-benchmarks/2026-09-20/prometheus-pretest-history.json),
[Kubernetes capacity inventory](../assets/fleet-benchmarks/2026-09-20/kubernetes-capacity.json)
and [optimistic placement model](../assets/fleet-benchmarks/2026-09-20/kubernetes-placement-model.json)
retain queries, timestamps and the assumptions behind the capacity tables.
Kubernetes evidence includes the [five direct volume probes](../assets/fleet-benchmarks/2026-09-20/kubernetes-direct-results.jsonl),
[enterprise-mirror probe](../assets/fleet-benchmarks/2026-09-20/kubernetes-enterprise-mirror-results.jsonl),
[SMB probe](../assets/fleet-benchmarks/2026-09-20/kubernetes-smb-results.jsonl),
[exact completed-test script](../assets/fleet-benchmarks/2026-09-20/kubernetes-benchmark.py)
and [first-attempt results](../assets/fleet-benchmarks/2026-09-20/kubernetes-buffered-first-attempt-results.jsonl).
Per-host preflight, benchmark counters and postflight JSON accompany them in the
same asset directory. The [NAS report](../nas-performance.md) owns its separate
method and evidence.

These are bounded observations, not a destructive media scan, an indefinite
stress test, or a failover drill. No raw VM logical volumes were opened for
benchmark writes. The host script uses exclusive temporary files, a two-minute
deadline, periodic flushes and cleanup; rerunning it still consumes real host I/O
and needs an appropriate maintenance window.

Before a consolidation change, record a representative busy period and backup
window, account for every sole data copy, check device and placement constraints,
and stage one app movement through GitOps. Verify its data and user-visible
behavior before retiring its old placement. Keep rollback storage and sufficient
capacity until recovery is proven. The
[disaster recovery runbook](../disaster-recovery.md) owns the recovery procedure.
