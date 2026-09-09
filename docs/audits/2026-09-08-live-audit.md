# The 2026 homelab inspection

**Purpose:** assess the running lab from physical disks through Proxmox, Talos,
Longhorn, applications and recovery, then identify the repairs worth doing.
**Status:** dated inspection and proposed repair plan; repairs are not deployed by
this report. **Evidence:** September 8 evening EDT / September 8–9 UTC, starting
23:41 UTC; individual samples retain their timestamps. The Git baseline was
`89f63c864`. This follows the September 5 audit and verifies what actually runs.

[Open the interactive inspection](../assets/inspection/index.html) to inspect
all seven physical machines, 24 drives, six Talos nodes, nine configured guests
(including stopped guests and Datacenter Manager), resource sizing, VPA,
replicas, PVCs and application health. The explorer contains a downloadable
sanitized inventory. [The previous lab tour](../lab.md) remains a historical
September 5 snapshot.

The lab has useful hardware and working automation. The most urgent faults are
**two memory-constrained processes repeatedly rereading executable pages from
disk, broken application data files, a failed backup, and gaps between reported
health and actual service recovery**. A blanket hardware replacement would miss
those faults. There are also real reasons to improve the control-plane storage
and plan the Elite data-drive replacement.

## 1. Disks: condition, placement and replacement priorities

All 24 physical drives were identified from the machines themselves. The 23
Proxmox/NAS drives reported SMART overall pass/OK; the Pi's NVMe SMART health log
reported no critical warning. That is one test result, not a clean bill of health.
Wear, interface errors, temperature, latency, pool layout and workload behavior
are assessed separately. The Pi health log was read directly through the Linux
NVMe Get Log Page API because neither smartctl nor nvme-cli was installed; no
package installation or disk change was needed.

### Physical inventory

| Host / device | Drive / capacity | Role | Health evidence | Assessment |
|---|---|---|---|---|
| HP SFF `sda` | PNY CS900 1TB SSD / 1,000 GB | Control-plane storage | 24,594h; 33°C | Upgrade first |
| HP SFF `sdb` | PNY CS900 1TB SSD / 1,000 GB | Proxmox + SFF worker | 24,769h; 33°C | Keep / plan data tier |
| HP Elite Mini `nvme1n1` | INTEL SSDPEKNW512G8 / 512 GB | Elite application data + PDM | 56,495h; 38°C; 74% endurance used; media errors 0 | Replace soon |
| HP Elite Mini `nvme0n1` | WDC PC SN530 SDBPMPZ-256G-1101 / 256 GB | Proxmox + Elite boot | 12,584h; 46°C; 1% endurance used; media errors 0 | Keep / watch power |
| Threadripper `sda` | PNY CS900 1TB SSD / 1,000 GB | Proxmox boot | 24,783h; 33°C | Keep |
| Threadripper `sdb` | MK000480GWCEV / 480 GB | Enterprise mirror member A | 52,829h; 16°C; reallocated 0 | Keep mirror intact |
| Threadripper `sdc` | MK000480GWCEV / 480 GB | Enterprise mirror member B | 48,105h; 18°C; reallocated 0 | Keep mirror intact |
| Threadripper `nvme0n1` | EDILOCA EN605 512GB / 512 GB | AI model cache | 22,107h; 54°C; 20% endurance used; media errors 0 | Keep |
| Threadripper `nvme1n1` | EDILOCA EN605 512GB / 512 GB | GPU VM boot + ephemeral + some Longhorn | 16,702h; 54°C; 14% endurance used; media errors 0 | Repair workload first |
| Dell OptiPlex `sda` | Samsung SSD 850 EVO 500GB / 500 GB | Dell Longhorn data | 74,175h; 39°C; reallocated 0; CRC 8,162 | Watch / demote role |
| Dell OptiPlex `sdb` | APPLE SSD SM0256G / 251 GB | Proxmox + Dell boot | 34,865h; 34°C; reallocated 0; CRC 0 | Keep / inspect adapter |
| HP Shed `sda` | PNY CS900 1TB SSD / 1,000 GB | Shed data device | 24,738h; 33°C | Reuse candidate |
| HP Shed `nvme0n1` | SK hynix BC501 HFM256GDJTNG-8310A / 256 GB | Proxmox + edge worker boot | 50,092h; 43°C; 4% endurance used; media errors 0 | Keep |
| TrueNAS DL360 `sda` | Samsung SSD 860 EVO 1TB / 1,000 GB | AI pool stripe member | 47,127h; 31°C; reallocated 0; CRC 4 | Keep / classify pool |
| TrueNAS DL360 `sdb` | T-FORCE 512GB / 512 GB | NAS boot mirror member | 26,861h; 33°C | Keep |
| TrueNAS DL360 `sdc` | MK000480GWCEV / 480 GB | NAS boot mirror member | 55,486h; 22°C; reallocated 0 | Keep |
| TrueNAS DL360 `sdd` | P3-512 / 512 GB | AI pool stripe member | 7,681h; 30°C; reallocated 0; CRC 0 | Keep / classify pool |
| TrueNAS DL360 `sde` | HP SSD S700 500GB / 500 GB | AI pool stripe member | 50,524h; 46°C; reallocated 0; CRC 816 | Inspect / watch |
| TrueNAS DL360 `sdf` | ST10000NM0096 / 10,001 GB | Secondary local backup pool | 57,533h; 34°C; grown defects 0 | Keep / recovery boundary |
| TrueNAS DL360 `sdg` | HUH721010AL4200 / 10,001 GB | BigTank mirror0 member | 7,504h; 38°C; grown defects 0 | Keep |
| TrueNAS DL360 `sdh` | HUH721010AL4200 / 10,001 GB | BigTank mirror1 member | 14,185h; 54°C; grown defects 0 | Inspect cooling |
| TrueNAS DL360 `sdi` | HUH721010AL4200 / 10,001 GB | BigTank mirror0 member | 7,771h; 49°C; grown defects 0 | Inspect cooling |
| TrueNAS DL360 `sdj` | HUH721010AL4200 / 10,001 GB | BigTank mirror1 member | 14,456h; 52°C; grown defects 0 | Inspect cooling |
| Raspberry Pi 5 `nvme0n1` | Patriot M.2 P300 256GB / 256 GB | Pi boot + management data | 13,323h; 33°C; 13% endurance used; media errors 0 | Keep / watch power |

Physical device names refer to this inspection. On the Threadripper,
**`nvme1n1` backs the volume group named `nvme0-vmstore`**, and `nvme0n1` backs
`nvme1-vmstore`. Following the volume-group name alone would select the wrong
SSD. The explorer shows the full device → VG → VM slot → Talos mount path.

### What is actually slow

A concurrent **120-second passive diskstats sample** across all physical hosts
found:

| Path | Observed workload and latency | Assessment |
|---|---|---|
| Threadripper EDILOCA `nvme1n1`, GPU VM boot/ephemeral | 620.7 MiB/s reads, ~10,987 physical read IOPS, 53.4 ms average read completion, 26.7 ms writes, 82% busy, average queue ~587 | Severe queueing associated with the faulty Temporal recovery Job. Repair its resource budget before judging the SSD's normal performance. |
| Threadripper HPE RAID1 | Each member ~108 write IOPS, 0.15–0.16 ms average write completion; ~1% busy | Healthy and responsive in this sample. Keep the mirror together. |
| SFF dedicated control-plane PNY | ~79 write IOPS, 3.78 ms average block-write completion, 15.6% busy | Modest throughput, but etcd's durable tail latency remains poor. |
| SFF worker PNY | ~195 write IOPS, 1.18 ms average writes, 5.7% busy | No sustained saturation in this sample; shares boot and application data. |
| Elite data Intel NVMe | ~18 write IOPS, 1.75 ms average writes, 0.9% busy | Wear is the replacement concern; the quiet sample does not show a current saturation fault. |
| Dell SSDs | Low activity during sample | Earlier 24-hour I/O pressure peaks are real, but cannot be labeled sustained physical-device saturation from a quiet two-minute window. |
| NAS BigTank HDDs | ~12–14 write IOPS per drive, ~1.1–1.2% busy | NAS was not the bottleneck during this sample. Cache and workload affect these observations. |

A block-write completion average does not measure durable `fsync` p99. Etcd's
histograms show **WAL fsync p99 43.8 ms**, with the worst five-minute sample over
24 hours **59.9 ms**; backend commit p99 **61.7–63.7 ms**. Etcd's troubleshooting
reference uses less than 10 ms WAL fsync p99 and less than 25 ms backend commit
p99 as useful checks. The SFF storage/guest/CPU path needs qualification; these
measurements do not isolate the PNY alone as the cause. [etcd FAQ](https://etcd.io/docs/v3.4/faq/)

### What to buy, keep and potentially move

| Order | Recommendation | Why and fit constraints |
|---|---|---|
| First repair, before buying | Fix the Temporal recovery Job and DCGM exporter memory budgets and retry/runtime behavior | They manufacture huge disk demand. A faster SSD would still be serving pointless rereads. |
| First disk purchase | A qualified **480 GB enterprise SATA SSD with power-loss protection** for the SFF's dedicated control-plane device | The CP guest is only 100 GiB. Buy durable low-queue-depth latency, not capacity. Micron 5400 PRO and Solidigm D3-S4620 are appropriate product families to compare; verify the exact part, seller SMART data and warranty/return terms. |
| Next planned replacement | **960 GB/1 TB class** Elite application-data replacement | Intel reports 74% rated endurance consumed, 56,495 hours and zero media errors. It currently holds a 440 GiB worker LV plus 10 GiB PDM LV. A nominal 480 GB disk is about 447 GiB and cannot hold those current allocations unchanged. |
| Fit-dependent Elite choice | Enterprise 2.5-inch SATA if its bay/caddy/cable are present; otherwise a compatible M.2 2280 NVMe with suitable endurance and thermals | HP documents 2.5-inch SATA and M.2 options for the model; SSH does not establish that this unit has its SATA hardware. Do not order M.2 SATA, U.2 or 22110 hardware on the assumption that all M.2-shaped products fit. |
| Keep | Both Threadripper HPE mirror members, its quiet model-cache NVMe, NAS HDD mirrors, Pi NVMe, WD/Hynix boot NVMe drives | No current media-error evidence justifies replacing them all. Reassess the busy EDILOCA after removing the artificial load. |
| Reuse candidate | Shed PNY data drive, or the displaced SFF CP PNY | The shed has zero Longhorn replicas and disk scheduling disabled, but ~17.6 GB filesystem use remains to classify. The SFF PNY becomes available only after successful CP migration. Treat both as conditional spares, not blank disks. |
| Leave in place initially | NAS's third HPE SSD | It is an active boot-mirror member. Harvesting it requires a replacement, completed resilver and boot verification first. It is not an unused spare. |
| Avoid spending first | Dell upgrades, more NAS RAM, or a larger GPU boot disk to hide reclaim | Dell remains temporary capacity. Global memory shortage was not found; no cache-device purchase has been justified. |

The [Micron 5400 documentation](https://www.micron.com/products/storage/ssd/data-center-ssd/5400-sata-ssd)
and [Solidigm D3 product brief](https://www.solidigm.com/products/data-center/product-briefs/d3-s4520-s4620.html)
are product-specification references, not current seller offers or proof a used
unit is healthy. [HP's model specifications](https://support.hp.com/sg-en/document/ish_5868243-5868287-16)
confirm supported storage categories; physical fit remains a pre-purchase check.

A no-new-drive route is possible in principle: qualify the shed PNY, use it as a
NAS boot replacement, finish resilver/boot validation, then qualify the freed HPE
for the CP and retain the displaced PNY. That couples several migrations and
failure domains to save one purchase. My preference is a dedicated CP purchase
and keeping the NAS stable. A 480 GB drive also cannot directly replace the
SFF worker's 690 GiB data LV or shed's 850 GiB LV; those need a new layout and
migration/restore, not an in-place shrink assumption.

### NAS, cache and shared-storage durability

- BigTank: two 10 TB mirrors, ~18.2 TiB pool capacity, 56% allocated, zero pool
  read/write/checksum errors at capture. The mirror pairs are `sdg+sdi` and
  `sdj+sdh`. HDD temperatures were 38, 49, 52 and 54°C. Inspect cooling on the
  hotter pair, especially during scrub; no over-temperature failure was proven.
- AI pool: three top-level SSD vdevs, ~1.82 TiB, 75% allocated. This is a stripe,
  so one member failure threatens the pool. It contains model/cache and
  `proxmox-flash` datasets; classify consumers before moving a member.
- Backup10T: one 10 TB Seagate, 68% allocated, zero grown defects/uncorrected
  errors. It is another pool in the same NAS, not an independent appliance.
- Boot: T-FORCE + HPE mirror, scrub September 8 repaired zero bytes/errors.
  AI/Backup10T recorded successful August scrubs with configured 35-day threshold
  schedules; an old-looking date alone does not mean scheduling is broken.
- ARC was ~215.6 GiB with substantial available RAM, zero memory-throttle count,
  and no current memory pressure. Keep the RAM. A warm snapshot does not establish
  minimum cache needs or justify SLOG/L2ARC purchases.
- **`BigTank/k8s sync=disabled` remains live**, inherited by many NFS/iSCSI
  application datasets. RustFS explicitly overrides `sync=standard`. This
  materially changes what an application `fsync` acknowledgement means; do not
  compare fast NAS results against local durable writes without this qualification.
- RustFS and Tailscale apps were Running; NFS, SMB, iSCSI and NVMe-target services
  were Running. A stopped historical Talos VM remains configured on the NAS.
  Its current TrueNAS build is `26.0.0-MASTER+20260902-020152`.

## 2. Memory and CPU: capacity versus harmful limits

The six Talos VMs have **65.7 allocatable vCPU / 222.7 GiB RAM**. Current container
measurements total **9.73 CPU cores / 74.9 GiB working set**, with scheduling
requests **35.1 cores / 117.5 GiB**. These exclude some OS costs and do not mean
all workloads can fit anywhere after a host fails. They do show that buying
blanket CPU/RAM capacity is not the first repair.

| Node | Pods | CPU allocatable / requested / used | RAM allocatable / requested / working set, GiB | CPU execution average / peak, 24h |
|---|---:|---|---|---|
| CP `.79` | 18 | 3.95 / 1.75 / 0.66 | 11.1 / 4.0 / 4.9 | 13.9% / 20.5% |
| Dell `.177` | 52 | 5.95 / 3.04 / 1.60 | 28.9 / 20.0 / 9.8 | 24.5% / 39.7% |
| GPU `.80` | 85 | 29.95 / 16.87 / 5.24 | 97.7 / 61.6 / 36.3 | 22.6% / 33.9% |
| Elite `.172` | 47 | 15.95 / 7.91 / 0.97 | 23.0 / 13.0 / 10.4 | 18.0% / 81.5% |
| Shed `.156` | 13 | 3.95 / 1.21 / 0.09 | 23.4 / 2.6 / 1.4 | 5.0% / 26.5% |
| SFF `.150` | 71 | 5.95 / 4.31 / 1.17 | 38.7 / 16.3 / 12.1 | 20.6% / 30.3% |

CPU execution excludes idle, I/O wait and steal. The SFF assigns 6 worker vCPU
plus 4 CP vCPU on a six-core physical CPU. Worker steal reached ~9.1%, CP ~6.1%
in five-minute historical samples. Review physical scheduling and burst demand
before adding guest CPUs. Elite had real short CPU contention despite modest
average use. The shed's idle capacity remains behind its network/device boundary.

The physical DIMM inventory is in the explorer: SFF has four 16 GB mixed DIMMs at
2133 MT/s, Dell mixed 8+16+8+8 GB at 2133, Threadripper eight 16 GB DIMMs at 2133,
Elite two 16 GB DDR5 DIMMs at 4800, shed two 16 GB at 2667, and NAS twelve 32 GB
ECC DIMMs reported at 1600. Different speed labels alone do not prove a fault;
no memory stress test or stability certification was performed.

### VPA is working

130 policies were inspected: 127 `InPlaceOrRecreate`, three `Off`; 127 have
recommendations. Metrics show approximately **124 in-place updates**, **37 applied
new-pod admissions**, and **one Frigate eviction** over 24 hours. No newly failed
in-place attempts or pending/deferred/infeasible pod resizes were found. Some
`*_total` updater metrics are gauges; zero currently eligible pods does not mean
zero historical activity. Four `NoPodsMatched` policies target verified parked
zero-replica workloads.

The useful fixes are at VPA's boundaries:

- StirlingPDF uses ~93% of its 1 GiB limit while VPA recommends 1.088 GiB.
  Prometheus recommends ~6.97 GiB under a fixed 6 GiB limit; Grafana recommends
  ~1.088 GiB under 1 GiB. `RequestsOnly` cannot raise these hard limits. Review
  Java/native memory and startup peaks before aligning budgets.
- Redis and Gitea Valkey have 150m CPU limits and ~32–36% throttled-period
  fractions despite ~25m average usage. These are quota hits, not a claim that
  36% of CPU time or user requests are lost. Compare application latency after
  correcting quotas; VPA cannot lift them.
- VPA does not manage the broken recovery Job, cannot fix its timeout, and never
  moves a pod to balance nodes. DaemonSets and generated workers also need their
  own sizing review.
- vLLM's VPA is intentionally Off. Both RTX 3090s were visible with ~21.4 GiB
  GPU memory allocated each, 220 W caps and 29–31°C at idle. Avoid applying a
  historical memory recommendation blindly; cold model loading and VFIO host
  pinning have different requirements from idle container working set.
- Radar tile-server's sole HPA correctly pairs CPU scaling with memory-only VPA,
  but `minReplicas=maxReplicas=1` means it cannot actually scale horizontally.

## 3. Spread, replicas and what happens when a machine stops

176 of 187 active Deployments/StatefulSets are single replica. That is a recovery
and interruption property, not a reason to blindly set every workload to three.
Stateful application semantics and RWO files must be handled first.

Current good physical spread includes 1Password (2), Cloudflared (3), Cilium
operator (2), CoreDNS (2), snapshot controller (2), and Longhorn CSI sidecars
(3 each). Cloudflared has physical-zone preferences. Most others use hostname
preferences, which do not automatically distinguish two VMs on the same chassis.

**Coroot Keeper's three Ready replicas all live on the same SFF worker VM.**
They provide no host-failure tolerance. The SFF also owns the sole CP, so SFF
loss removes Kubernetes scheduling/control and many applications together.
For control-plane host-loss tolerance, plan three control-plane members on three
qualified physical hosts; two etcd members or three VMs on one chassis do not
solve it. Keep that as a deliberate remodel decision, not an automatic upgrade.

### Longhorn: healthy often means one healthy copy

80 Longhorn volumes: 78 configured with one replica, two with two. One of the
two-copy volumes is an old Released Temporal volume. **Only one current PVC,
Temporal Postgres, has two copies**, currently on Elite and SFF. The 71 attached
volumes were healthy; nine detached volumes were unknown, often parked/retained.
Unknown while detached is not itself a failure. Replica CR count also includes
failed/stopped remnants and must not be counted as surviving writable copies.

The mirrored HPE disks protect a physical-disk failure within the Threadripper;
they do not protect losing that host, VM, controller or power. A Longhorn volume
can serve a pod on another node while still having its only data copy on the GPU
host. See every PVC's actual replica host/path in the explorer.

Prioritize complete services on wired, qualified hosts: database, application
files, queue semantics and enough surviving compute. Budget two copies plus
snapshots, restore staging and rebuild space. Do not reduce the existing
overscheduling allowance until provisioned capacity, rebuild headroom and migration
requirements are validated. Do not move only the database while leaving required
files single-copy elsewhere. The five Longhorn instance-manager PDBs protecting one
manager per node are intentional storage safeguards; blanket removal is not a
repair.

### A real maintenance event during this inspection

Proxmox logs show `root@pam` updated Elite VM100's Coral USB passthrough at
**23:36:11 UTC**, stopped VM100 at 23:36:14 and started it at 23:36:29. The physical
host did not reboot. Talos became Ready around 23:37:07, but storage recovered
through ~23:40. Thirty-second metrics sampled **22 faulted Longhorn volumes**
at 23:38:31, then zero after recovery. Alerts retained those faults for their
configured ten-minute window; they were not false alarms.

This establishes a requested VM stop/start, strongly associated with the Coral
configuration change; the account log does not establish which person/session
requested it or whether a drain was attempted. The later PDM container reboot
at 23:42:44 was a separate event. Flatnotes was already crashing before the
storage event, so it cannot be blamed on that later restart.

**Repair implication:** Ready after reboot and automatic salvage are not proof
that every application file survived. Establish a planned maintenance path with
surviving replicas, fencing and application checks before repeating power cycles.

## 4. Disk thrashing: the two confirmed software faults

### Temporal recovery CLI

The five-minute maintenance CronJob has one run stuck since **04:05 UTC**.
It is still in its first read-only `temporal worker deployment list -o json`
command; it has not reached the script's identity-changing operation.

- Container limit: 128 MiB; executable: 549.5 MiB.
- Memory current: 133.85 / 134.22 million bytes; file cache ~128.1 MB, anonymous
  memory only ~3.1 MB.
- File-page refaults: 10.565 billion; direct page scans: 17.533 billion; major
  faults ~713,000.
- Process I/O: **43.277 TB read, zero writes over ~19h45**; zero OOM kills in this
  run. Read traffic is not flash TBW write wear.
- Physical path: GPU `.80 /dev/sda` → VM103 `scsi0` → `nvme0-vmstore` → host
  `nvme1n1`. The other model-cache NVMe and HPE mirror were much quieter.

Linux is repeatedly discarding and rereading file pages to execute within the
small cgroup budget. A small reported working set and no OOMKilled event conceal
that failure. `concurrencyPolicy: Forbid` blocks later maintenance behind it;
`startingDeadlineSeconds` does not stop an already-running Job.

**Repair:** give the CLI a measured startup/runtime memory budget, bound each
command and add `activeDeadlineSeconds` in Git. Then replace the existing stuck
run and compare completion time, refault rate, host queue and latency. A candidate
larger limit must be validated; executable file size alone is not the resident
memory requirement. This is the first repair to validate before buying GPU storage.

### DCGM exporter

The exporter had ~158 restarts in 24 hours and only **68.7% scrape success**.
Explicit liveness events explain its exit-137 restarts; do not call every 137 an
OOM. Its persistent **pod parent cgroup**, capped at 512 MiB, exposes:

- 9.62 billion file refaults, ~7.92 million major faults;
- **39.48 TB reads since the pod's September 3 creation**;
- 6,277 seconds of full memory stalls and ~161 million memory-limit boundary
  events; zero OOM kills.

A freshly restarted child container looked quiet because those parent counters
persist across container restarts. This is a second confirmed historical reclaim
storm, although its lifetime totals are not the current read rate. Correct the
pod/container resource budget and verify steady exporter behavior under GPU load.
The two GPUs themselves were visible and healthy in the limited `nvidia-smi`
inspection; exporter failure is not a GPU hardware diagnosis.

## 5. Argo, ApplicationSets and monitoring complexity

### Keep the reconciliation architecture; make its signals more meaningful

All 100 Applications were Synced; a repeated check found 96 Healthy and four
Progressing. Metrics recorded ~42 successful syncs and zero failed syncs in 24
hours. The repaired directory discovery, component exclusions, bounded retries,
`missingkey=error`, `FailOnSharedResource`, and app-owned resources are useful.
There is no evidence here that changing GitOps platforms would repair the lab.

Recommended focused changes:

1. **Make runtime health actionable.** Keep sync status separate from useful
   app health: a Synced Redis deployment can still have an unreadable AOF.
   Custom health for controller CRs should reflect conditions/progress, not a
   blanket green status. Pair important apps with representative transactions.
2. **Audit the remaining broad diff exceptions by owner and field.** Keep
   legitimate immutable PVC restore exceptions; narrow obsolete image-pull-policy,
   HTTPRoute-weight, CRD-conversion and instrumentation exceptions only after
   comparing rendered and live objects. Do not remove them wholesale and recreate
   the immutable-PVC sync failures already solved.
3. **Test shared-component change detection.** App annotations name their app
   path, while shared Kustomize components can change outside it. Ensure CI renders
   impacted consumers and webhook/path optimizations do not hide shared changes;
   periodic reconciliation should remain a fallback.
4. **Treat waves as object ordering, not complete service readiness.** ApplicationSet
   creation waves do not automatically health-gate all generated children. Prefer
   bounded dependency retries and explicit readiness for app startup. Evaluate
   progressive sync only for a named dependency problem, with cold-bootstrap and
   recovery tests; do not add another manual sync gate to every app.
5. **Review the database ApplicationSet's deliberate `selfHeal: false`.** Live/Git
   configuration should explain the current Redis/shared-support scope after the
   CNPG retirement. Determine whether that exception still serves a purpose;
   review separately from restore-field exceptions.
6. **Keep changes reviewable.** Runtime repairs, hardware layout, autoscaling and
   observability each need focused PRs with an acceptance test. Do not mix an
   infrastructure major-version jump into the recovery repair.

### Which monitoring apps earn their place?

Current aggregate container working sets and CPU provide a starting cost ledger,
not a judgment of value:

| Namespace / purpose | Working set | CPU cores now | Recommendation |
|---|---:|---:|---|
| Prometheus stack | 4.26 GiB | 0.45 | Keep metrics/Grafana; repair exporter and add physical-health coverage. ~519k active series does not by itself prove bloat. |
| Coroot | 2.60 GiB | 0.30 | Require a concrete daily use case for its additional storage/database/quorum. Fix same-host Keeper placement if retained for availability. |
| Loki | 1.39 GiB | 0.09 | Keep if centralized logs are used; scrape its own metrics and validate retention/S3 outage handling. Review distributed topology versus a simpler deployment at this measured scale. |
| OTEL | 0.97 GiB | 0.31 | Log transport is active (~123 records/sec). Add bounded durable queues where outage loss matters; avoid duplicate Kubernetes metrics collection. |
| Keep | 1.17 GiB | 0.04 | It must reliably deliver/action alerts to justify another database/service chain. Fix observed 401 authentication failures first. |
| Tempo container | 0.035 GiB | 0.004 | Ready but zero trace batches since process start September 5. Either instrument one useful workflow and use it, or park it through Git after confirming no consumer. |

Tempo is a small memory consumer here; parking it would simplify operations more
than reclaim RAM. PostHog consumes ~9.57 GiB and 18 containers; Langfuse ~2.36 GiB. They serve
application analytics/LLM telemetry, so their value should be assessed against
actual use rather than treating all observability as interchangeable. Parked
apps are not evidence of current CPU waste, though retained PVCs and monitoring
objects still need ownership. Holmes remains on-demand; avoid an always-running
AI investigation loop as a substitute for correct alerts.

My preferred simplification is **one trusted metrics/alert view, one useful log
path, and tracing only for an actual consumer**. Start by eliminating broken or
unused targets and duplicate functions; do not add another full monitoring stack
before using the signals already available.

## 6. Pod health, alert delivery, Postgres and recovery

### Repairs with directly observed application impact

- **SurfSense Redis:** malformed AOF at byte offset 36,151,654 prevents startup.
  Its worker nevertheless reports Ready and repeatedly logs broker connection
  refusal; it lacks meaningful readiness/liveness. Preserve the AOF before
  choosing recovery/truncation/reset, decide acceptable queue loss, then validate
  real background work. Dependency-aware readiness/heartbeat is useful; repeatedly
  killing workers because Redis is down would worsen the outage.
- **Flatnotes:** persistent Whoosh index parse reaches EOF and the pod crash-loops.
  Preserve note data and index, validate an index-only rebuild path, then check
  notes/search. The SSD corruption cause is not established.
- **Perplexica backup:** last success September 7 ~03:10 UTC, ~44.6 hours old at
  capture. `config.json` is uid0:gid568 mode0600; mover568:568 cannot read it.
  The schedule says Ready with zero consecutive failures while its Snapshot
  failed. Fix app file ownership plus mover contract and verify a new nonempty
  backup. Do not change the mover to root as a shortcut.
- **Temporal:** timer DLQ metric reports five messages. Classify age and affected
  workflows before replaying; do not purge unexplained work.

84 of 187 active Deployment/StatefulSet workloads have at least one container
without readiness, and 83 without liveness. This includes workers and fixed
sidecars, so it is a triage inventory, not 84 proven incidents. Fix checks around
real failure modes: queue progress, an application read/write, storage availability,
DB connectivity, and stalled work. A `/metrics` listener or `ls /` probe is not
proof the service can perform its job.

### Monitoring is collecting useful data, but misses important failures

- No Prometheus targets for Proxmox/NAS physical disks, SMART, NVMe wear, ZFS pool
  health, or Loki/Tempo themselves. Node-exporter inside Talos sees virtual and
  Longhorn devices; it cannot report physical SSD wear or distinguish its backing
  without this inventory.
- Three real Alertmanager deliveries to Keep failed HTTP401 around the storage
  incident. Other attempts existed; this does not establish total delivery failure.
  Repair authentication and perform a controlled end-to-end test. This audit sent
  no notifications.
- The alert chain shares cluster dependencies; Watchdog routes to null. Add a
  small independent external deadman/HTTP check so a failed cluster can be noticed
  without relying on its own Alertmanager, Keep and databases.
- The old llama ServiceMonitor scrapes a deleted IP retained in Endpoints and
  EndpointSlices although the service now aliases vLLM. Its 24-hour success is
  zero; the actual vLLM target is up. Retire stale discovery through the owning
  GitOps change instead of diagnosing the model server as down.
- `PodNetworkUnavailable` really tests Running-but-not-Ready. Rename/remove the
  misleading duplicate; Flatnotes index errors are not a network diagnosis.
- OTEL queues are memory-only with 30-second retry ceilings. Current log flow
  works; this does not establish durability across a NAS/gateway outage. Tempo
  readiness returned200, but its process had received zero trace batches.
- Cilium currently reports all six nodes/endpoints reachable; three gateways are
  programmed, all 71 HTTPRoutes have acceptable conditions, and nine certificates
  are Ready. Shed Cilium had ~48 restarts/24h waiting for initial cluster policy
  resources; correlate its bridge/link/API availability rather than merely
  lengthening timeouts. Keep critical state off that edge path.

### Backups and restore evidence

90 PVCs: 35 matched SnapshotPolicies, 46 explicit backup exemptions, nine live
classification gaps (six Coroot, two Loki, registry). A classification gap does
not automatically mean data needs Kopia backup; document intentional disposability
and observe system-namespace exceptions.

34 of 35 policies had success ages consistent with their schedules; Perplexica
is the active stale failure. The 85 Failed retained Snapshot CRs are cumulative
history, not 85 currently broken backups. Nine Postgres policies already run a
CHECKPOINT before filesystem snapshot, a useful improvement. Database and WAL
placement, durable settings and restore verification are examined separately.

35 Restore CRs say Completed, but **31 resolved an actual snapshot and four used
`NoSnapshot`**, the deliberate continue-empty path. Completed must not be counted
as 35 demonstrated restores. The four are Langfuse ClickHouse/Postgres and
SurfSense object store/Postgres; this audit does not infer accidental data loss
from those intentional bootstrap outcomes.

The restore canary reports quick verification September 6 10:13 UTC. Its actual
Restore hydrated an August 24 snapshot. That is useful historical evidence,
**not a fresh full-service restore test**. Kopiur's backend-down Pending safety
must remain intact. Hourly/daily snapshots also do not provide arbitrary
point-in-time database recovery by themselves.

### PostgreSQL: sound write settings, incomplete visibility and recovery coverage

All ten instances accepted connections. `fsync`, `full_page_writes`,
`synchronous_commit` and autovacuum are enabled everywhere. No blocked locks,
long client transactions, deadlocks or near-term transaction-ID wraparound risk
were found. Data and WAL share one PVC on every instance, with no external
tablespaces. Total non-template database size is approximately **6.31 GiB**.

| Instance | Server version | Data size, MiB | Checksums | Longhorn copies | Backup cadence | Actually scraped |
|---|---|---:|---|---:|---|---|
| gitea | 18.6 | 29.1 | on | 1 | Hourly | Yes |
| hindsight | 16.15 | 16.5 | off | 1 | Daily | No |
| immich | 17.6 | 148.6 | on | 1 | Hourly | No |
| intercept | 18.6 | 2,522.6 | on | 1 | Hourly | No |
| keep | 18.6 | 126.4 | on | 1 | Exempt | No |
| langfuse | 18.6 | 20.2 | on | 1 | Hourly | No |
| paperless-ngx | 18.6 | 22.6 | on | 1 | Hourly | Yes |
| posthog | 15.12 | 2,587.2 | off | 1 | Daily | No |
| surfsense | 17.11 | 196.9 | on | 1 | Hourly | No |
| temporal | 17.11 | 794.6 | on | 2 | Hourly | Yes |

**Five databases crash-recovered:** Gitea, Immich, Intercept, Keep and Temporal
completed WAL recovery between 23:39:49 and 23:40:22 UTC. Their replacement pods
show zero container restarts, illustrating why restart counters alone miss
service interruptions. Keep recovered just before the first rejected alert;
that is a useful investigation lead, not proof of the 401 cause.

**Upgrade two minor versions:** Immich PostgreSQL 17.6 and PostHog 15.12 miss
current fixes, including authenticated code-execution vulnerability
CVE-2026-14669. Current minors at inspection are 17.11 and 15.19. Prepare
application-compatible image updates, preserving Immich's VectorChord extensions
and PostHog's supported self-hosted upgrade path. No exploitation was attempted
or observed. [PostgreSQL advisory](https://www.postgresql.org/support/security/CVE-2026-14669/),
[version policy](https://www.postgresql.org/support/versioning/).

**Fix monitor discovery:** PostHog's PostgreSQL, ClickHouse and Kafka Services
lack the metadata labels their ServiceMonitors select. Labels inside a Service's
`spec.selector` choose pods; they do not label that Service. These exporters are
absent from discovery rather than visibly down. Add the correct Service labels
in Git and verify target presence. Extend intentional PostgreSQL monitoring
beyond Gitea, Paperless and Temporal.

All ten databases disable `track_io_timing` and `track_wal_io_timing`; zero timing
counters therefore cannot establish fast disks. Enable useful timing after a
small overhead check, and track connections, locks, transaction age, checksums,
WAL retention, database/PVC growth and recovery freshness.
[PostgreSQL statistics](https://www.postgresql.org/docs/17/monitoring-stats.html).
Hindsight and PostHog also disable page checksums. Plan checksum enablement during
verified maintenance/restore; these versions require the database offline for
`pg_checksums`. The other eight report zero checksum failures on pages examined,
not a complete integrity scan.
[Checksum documentation](https://www.postgresql.org/docs/15/checksums.html).

**Protect recovery points deliberately:** nine PostgreSQL volumes have full-PVC
snapshot policies and CHECKPOINT hooks. Keep is explicitly exempt because alert
history is disposable and providers/workflows are reconstructed from Git.
Seven databases have hourly backups; Hindsight/PostHog are daily. None archives
WAL or has a physical standby, so current snapshots do not provide point-in-time
recovery. Add WAL archiving/base-backup support only where the agreed data-loss
window warrants it, within the existing plain-Postgres architecture.
[PostgreSQL PITR](https://www.postgresql.org/docs/17/continuous-archiving.html).

The same-volume data/WAL geometry supports a consistent filesystem snapshot.
**CHECKPOINT reduces recovery work; the atomic snapshot supplies consistency.**
Independent snapshots of database, object storage and application files are not
a transactionally coordinated full-service backup.
[Filesystem backup requirements](https://www.postgresql.org/docs/17/backup-file.html).
A fresh isolated restore was not performed in this inspection. The next drill
should hydrate a selected backup into a matching-major, extension-compatible
clone with production network paths blocked, verify WAL recovery and integrity,
then run application smoke checks against paired files/object storage and keys.
Restore both Temporal databases together. Measure actual recovery time and
accepted data loss rather than assigning them from a schedule alone.

SurfSense's Zero logical slot is active with only 56 bytes retained, but
`max_slot_wal_keep_size=-1` permits unlimited retention if its consumer stops.
Set a deliberate retention/reinitialization policy and alert before WAL fills
the PVC. This feed is not a physical HA standby.

The two-minute passive sample found no new WAL-buffer-full events or temporary
spills. Temporal averaged ~24.65 commits/sec and ~30 KiB/sec WAL; PostHog
~8.32 commits/sec and ~4.19 KiB/sec. These small current workloads do not justify
buying database CPU/RAM before fixing storage and recovery. Buffer-hit ratios
and checkpoint write durations are not substitutes for durable disk latency.


## 7. Repair order and acceptance tests

| Priority | Work | What closes it |
|---|---|---|
| Repair first | Temporal recovery CLI memory + command/Job deadlines | Run finishes within cadence; following scheduled run succeeds; refault/read/queue/PSI rates collapse. |
| Repair first | DCGM parent/container sizing and health | Sustained healthy scrape under representative GPU load; restart and reclaim rates stop growing abnormally. |
| Repair first | Preserve and recover SurfSense Redis and Flatnotes | Actual background jobs, notes and search work; app checks reflect dependency failure. |
| Repair first | Perplexica owner/mover mismatch and Keep auth | New nonempty backup plus restored sample; real alert delivery verified. |
| Repair first | Immich/PostHog PostgreSQL minor fixes and missing monitor discovery | Compatible minor images pass an isolated recovery/smoke check; intended database/exporter targets appear and scrape. |
| Qualify next | CP SSD and guest CPU scheduling | Comparable etcd p99 improves, existing CP disk retained as rollback until verified. |
| Plan next | Elite data replacement and physical health telemetry | Capacity/fit verified; SMART baseline, tested migration and alerts for wear/errors/temperature. |
| Redesign selectively | Important app state on distinct wired hosts, quorum spread and planned maintenance | Bounded canary host loss/return proves fencing, surviving data and app behavior; then apply to agreed service groups. |
| Simplify | Monitoring overlap, unused tracing and stale targets | Fewer dependencies while retaining metrics, logs and verified alert delivery; explicit use case for every retained stack. |
| Prove recovery | Isolated restore of a complete important service | Database + files + queue expectations verified; record measured interruption and data-loss window. |

Do repairs in small PRs. A clone/restore drill needs a concrete isolated target,
known backup identity and acceptance query; a replica change needs enough space
for surviving copies, snapshots and rebuilds. Keep production and recovery
sources untouched until validation succeeds. Refer to the existing
[disaster-recovery runbook](../disaster-recovery.md),
[storage architecture](../storage-architecture.md), and
[VPA/scheduling guide](../domains/scheduling/vpa-and-topology.md) for canonical
operating procedures.

### Other host inspection items

The Threadripper's `gpu-reset-method.service` is failed and contains an old PCI
address (`0a:00.0`) while the second passed-through GPU is now `43:00.0`. Current
reset-method files advertise FLR and both GPUs are visible; a failed boot helper
is a maintenance-path defect to reconcile, not proof the running GPUs failed.
The Pi's `chrony-wait` failed during boot, but current chrony/timedatectl report
synchronized time with ~0.38 ms offset. Record the boot warning without calling
current timekeeping broken.

## Measurement limits and benchmark appendix

This was live-system inspection during ordinary activity and externally requested
VM maintenance. It did not isolate every load generator or certify unused
hardware. There was no raw-device write, global cache drop, stress test, node
power-off experiment, production database rewrite, or application repair.
Bounded temporary-file benchmarks, where performed, are listed below with their
exact path, semantics and cleanup result. They are latency comparisons under the
observed workload, not maximum-throughput certifications.

### Bounded filesystem latency and cache probes

Six successful paths were tested sequentially through existing containers or
NAS SSH. Each probe created its own exclusive UUID-named temporary file, used
100 samples of 8 KiB append plus `fsync`, capped synchronous operation rate at
100 IOPS, then wrote and read 8 MiB at a maximum 4 MiB/sec. A repeat read explored
warm-cache behavior. These are short probes under current load, **not saturation
benchmarks, PostgreSQL transaction latency, or power-cut durability tests**.

| Tested path | p50 fsync, ms | p95, ms | p99, ms | Interpretation |
|---|---:|---:|---:|---|
| HPE mirror / Longhorn | 5.01 | 6.26 | 7.35 | fsync requested through Longhorn; 100 paced 8 KiB append + fsync samples; own file removed. |
| Dell Samsung / Longhorn | 9.77 | 12.15 | 12.56 | fsync requested through Longhorn; 100 paced 8 KiB append + fsync samples; own file removed. |
| GPU boot NVMe / Longhorn | 5.93 | 107.81 | 172.12 | fsync requested through Longhorn; 100 paced 8 KiB append + fsync samples; own file removed. |
| NAS SMB / CSI | 3.41 | 4.67 | 4.88 | ZFS sync disabled; Acknowledgement only; not a durable-commit comparison. |
| NAS BigTank / direct | 7.14 | 19.36 | 27.32 | ZFS sync standard; Server-local filesystem probe; excludes network/CSI. Own file removed. |
| NAS AI pool / direct | 1.25 | 3.18 | 3.25 | ZFS sync standard; Server-local filesystem probe; excludes network/CSI. Own file removed. |

The Longhorn HPE test used Radar worker `/data/state` → GPU Talos `sdc1` →
VM103 `scsi2` → thick LVM → `md0` HPE RAID1. Dell used OpenWebUI's data PVC →
Talos `sdb1` → Dell Samsung 850 EVO. GPU boot used TubeSync's `/config` PVC →
Talos ephemeral `sda4` → VM103 `scsi0` → physical EDILOCA `nvme1n1`.
All three had one Longhorn replica, so this does not predict two-copy latency.

The GPU boot path's median was deceptively acceptable while p99 reached **172 ms**,
consistent with the independently observed reclaim/queue problem. Its first-read
maximum was ~90 ms versus ~0.165 ms on the warm repeat. First-read and warm-repeat
checksums matched on all successful paths. File-specific `DONTNEED` was advisory:
it did not flush server/controller caches, so “first read” is not proven cold
physical media. The 4 MiB/sec rate was imposed by the probe, not a network limit.

**The SMB result is not equivalent durable storage.** TubeSync's `/downloads`
uses SMB CSI/CIFS 3.1.1 to `BigTank/k8s/tubearchivist`, inheriting `sync=disabled`.
It acknowledges flushes without the stable-storage guarantee expected from
synchronous writes. The client also uses `cache=loose`, `soft`, 60-second attribute
caching and multichannel. Review cache coherency against actual multi-client
writers and durability against the dataset's role; do not copy these settings
to PostgreSQL. [Linux CIFS mount options](https://www.samba.org/samba/docs/current/man-html/mount.cifs.8.html).
The server-local BigTank and AI probes used `sync=standard` and excluded network
and CSI overhead. The faster AI-pool result does not repair its unprotected
three-vdev layout.

**NFS configuration was inspected, but its scratch-file read test was blocked.**
Immich's existing NFS mount is read-only, NFS 4.1, `hard`, `nconnect=16`, 1 MiB
read/write sizes and `noatime`, from Dell to `BigTank/photos/All`; the dataset has
`sync=standard`. One exclusive 8 MiB NAS scratch file was created for a read-through
probe, but Immich received `EACCES` opening that new file. The test therefore
produced no NFS throughput result. Mode 0644 alone does not override dataset ACLs
or mount identities. Review that identity/ACL contract before a future canary;
this does not prove existing photos are unreadable. No existing media was read.

All seven scratch files, including the blocked NFS probe, were removed after
checking their original inode ownership/identity; absence was confirmed. No raw
disk writes, global cache drops, mount changes or ACL changes were performed.
The tested Longhorn volumes remained healthy after the successful probes.


The private evidence directory contains timestamped object snapshots, source
queries, SMART/diskstats and process/cgroup observations. Published files are
sanitized projections; no credentials, disk serial numbers, raw configs or app
content are included. Historical 24-hour maxima were sampled at five-minute
steps; short spikes can be missed, and metrics gathered at different times may
not sum exactly. No single benchmark proves power-loss durability or successful
full-service restore.
