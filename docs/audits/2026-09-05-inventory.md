# Repository and physical inventory — 5 September 2026

[Explore these machines interactively](../lab.md): hosts, guest IPs, all physical
drives, VM allocations and a dependency walkthrough.

**Status:** observed inventory and owner-confirmed constraints. This is a dated
audit snapshot, not a replacement for the owning manifests or recovery runbooks.
See the [architecture audit and proposed PRs](2026-09-05-architecture-audit.md).

After this snapshot, the owner merged Fizzy/Mailpit removal in PR #2238.
Their Applications and namespaces are gone; the original inventory remains dated. The
CSV inventories deliberately preserve what was observed before that removal.

## Repository inventory

| Inventory | Result / download |
| --- | --- |
| Discovered child Applications | 98: 18 standalone core entrypoints, 14 infrastructure, 2 database, 9 monitoring, 55 user apps. [CSV](2026-09-05/applications.csv) |
| Live Argo Applications | 99 including root; 98 Synced/Healthy, Project Nomad Synced/Progressing at collection. |
| Kustomizations rendered | 102 under infrastructure/monitoring/my-apps, including one intentionally empty Component. |
| Static workload controllers | 164 Deployments, 9 StatefulSets, 12 DaemonSets, 23 Jobs, 7 CronJobs. Operator-generated children are not included in this count. [253 container rows](2026-09-05/workloads.csv) |
| Live pods | 282 in the collected snapshot: 278 Running, 4 Succeeded; 223 Burstable, 59 BestEffort. Running is not synonymous with all containers Ready. |
| Storage | 77 PVCs in the expanded app render; 88 live PVCs including controller-created and transient claims. [Live claim inventory](2026-09-05/live-volumes.csv) |
| Backup contract | 34 SnapshotPolicy/SnapshotSchedule/Restore bundles; zero broken links and zero coverage warnings. Live backup-success age series existed for all 34 policies. |
| Routing | 69 HTTPRoutes, 3 Gateways. [Route/backend inventory](2026-09-05/routes.csv) |
| Monitoring | 38 rendered ServiceMonitors, 2 PodMonitors, 42 PrometheusRules, 125 VPAs, 5 PDBs. Live: 44 ServiceMonitors, 83 discovered scrape targets, all up. Missing discovery remains a separate defect. |
| Documentation | 52 Markdown pages under docs before this audit; 112 tracked Markdown files across root, docs, app directories, Omni and agent instructions. [Path/title inventory](2026-09-05/documentation.csv) |

Static counts use CI's default Helm capabilities. Argo also supplies the cluster
API versions; a second render with monitoring capabilities correctly produces its
four live Argo ServiceMonitors. Static counts are therefore not the full runtime
inventory. The aggregate CI render also counts some nested resources twice. The app inventory
expands actual discovery paths and checks ownership instead; no duplicate resource
ownership was found. CSVs omit environment values, Secret contents, serial numbers
and raw command output. They contain infrastructure names and private addresses
where these are necessary to describe deployment and placement.

## Physical hosts and failure domains

Addresses below use the `192.168.10.0/24` LAN. Hardware models were read from SMBIOS;
VM placement, disks and RAM were read from Proxmox. RAM is installed/configured
capacity, not a promise of schedulable Kubernetes memory.

| Physical host | Role / RAM | Storage observed | Operational implication |
| --- | --- | --- | --- |
| `.14` Threadripper | ~128 GB; Talos GPU VM 100 GiB, 30 vCPU; Kali VM stopped | PNY CS900 1 TB Proxmox boot; two HPE MK000480GWCEV 480 GB SATA SSDs in md RAID1/thick LVM; two EDILOCA EN605 512 GB NVMe devices | Enterprise pair backs 300 GiB Longhorn flash plus a separate 120 GiB virtual disk. One NVMe backs Talos boot/ephemeral Longhorn; the other backs local AI model cache. Two mirrored drives still share one host failure domain. |
| `.16` Dell OptiPlex 7060 | ~40 GB; Talos worker 30 GiB, 6 vCPU | Apple 251 GB boot SSD; Samsung 850 EVO 500 GB with 400 GiB thick data LV | Owner describes an exposed motherboard on acrylic, an adapted MacBook SSD and an improvised cooler; temporary capacity, not long-term quorum hardware. Samsung has ~74,097 power-on hours and 8,162 historical CRC errors, without reported reallocated/uncorrectable errors. CRC history alone does not prove current failure; qualify connection and stability before trusting the node. |
| `.20` HP ProDesk 600 G4 DM, shed | ~32 GB; live Talos VM 25,000 MiB, 4 vCPU | SK hynix BC501 256 GB boot NVMe; PNY CS900 1 TB with 850 GiB data LV | Ethernet behind ASUS Wi-Fi media bridge. Longhorn data scheduling disabled and no replicas scheduled. Git machine-class RAM is 12 GiB, so live VM allocation differs. Not a quorum/storage HA candidate by default. |
| `.21` HP ProDesk 600 G4 SFF | ~64 GB; worker 40 GiB/6 vCPU and sole control plane 12 GiB/4 vCPU | Two PNY CS900 1 TB SATA devices. One has only the 100 GiB CP LV, leaving ~831 GiB VG free; the other holds Proxmox plus worker boot 128 GiB/data 690 GiB in thick LVM | Worker and control plane are one failure domain. CP device capacity is mostly unused, but the useful upgrade is durable small-write latency. Avoid filling that spare capacity with bulk work and recreating contention. |
| `.22` HP Elite Mini 600 G9 | ~32 GB; Talos worker 24 GiB, 16 vCPU | WD PC SN530 256 GB boot NVMe; Intel SSDPEKNW512G8 512 GB data NVMe with 440 GiB data LV | Intel reports 74% estimated endurance used, 56,418 hours, 539 unsafe shutdowns, zero media errors. Stronger replacement candidate than age alone. Do not assume a 2.5-inch SATA purchase fits this Mini without checking its drive bay/caddy. |
| `.15` Raspberry Pi 5 | ~8 GB; Omni and Technitium DNS, owner confirmed | Patriot P300 256 GB NVMe; approximately 210 GB free in the inspected filesystem | Shared external management/DNS failure domain. It is not running from an SD card in this inventory. |
| `.133` TrueNAS DL360 | Owner: one Xeon, stable NAS role; OS sees ~378 GiB RAM and 28 logical CPUs | Four 10 TB HGST disks in two mirrors; separate single 10 TB Seagate backup disk; mixed SSD AI pool; mirrored SSD boot pool | RustFS and NAS data are deliberately outside Kubernetes. Owner accepts service stalls during NAS maintenance. Keep general compute repurposing secondary. |

The NAS has a **third HPE MK000480GWCEV 480 GB SSD**: `/dev/sdc`, one half of the
boot mirror with a T-FORCE 512 GB SSD. The Threadripper's pair is not the only
enterprise SATA hardware already owned. Reusing this boot device for etcd is a
possible future disk-placement plan, but requires a tested NAS boot replacement,
configuration/key backup and completed resilver first. It is not a spare disk to
pull from a running NAS.

## Disk observations and their limits

A concurrent 30-second `/proc/diskstats` sample on all five Proxmox hosts and the
NAS found no sustained device saturation. The Threadripper's HPE mirror members
each handled approximately 366 write IOPS at 0.15 ms average write completion;
the Elite data NVMe handled about 179 write IOPS at 0.12 ms. These are observed
block-layer averages under that workload, **not durable fsync benchmarks**.

The SFF had approximately 3.4% IO "some" pressure and 2.2% IO "full" pressure over
five minutes. Its control-plane PNY device averaged about 99 write IOPS at 2.38 ms
in the short sample. Independent etcd histogram queries found WAL fsync p99 near
49 ms and backend commit p99 near 62 ms. Averages and p99 describe different parts
of the latency distribution; the low average does not dismiss the etcd result.

All inspected Proxmox drives reported SMART overall pass. That does not establish
power-loss protection, predict remaining lifetime, explain historical corruption,
or rule out a controller/cable/firmware issue. Vendor-specific PNY/HPE attributes
were not interpreted as generic NAND-failure counts. The report does not attribute
Gitea's prior zero-byte Longhorn metadata file to a specific SSD.

Longhorn's observed free space is substantial: approximately 382 GiB Dell, 422 GiB
Elite and 655 GiB SFF data-disk free space. Those are filesystem free bytes, not
unallocated Proxmox VG space. GPU flash had about 153 GiB free but 415 GiB of
declared scheduled capacity on a 300 GiB disk. The existing 200% scheduling allowance
also supports restore staging; do not blindly reduce it to 100%. Capacity planning
must include snapshots, second replicas, staging, and simultaneous rebuild demand.

## TrueNAS pools, ARC and electricity

| Pool | Observed layout / use | Meaning |
| --- | --- | --- |
| BigTank | Two mirrored pairs, ~18.2 TiB pool size, 55% allocated, no reported data errors | Main NAS/RustFS storage. No dedicated SLOG, L2ARC or special vdev appeared in pool status. |
| Backup10T | One disk, ~9.08 TiB, 68% allocated, no reported data errors | A second local pool, not a second appliance or proof RustFS is replicated there. |
| ai-pool | Three top-level SSD vdevs: HP S700 500 GB, P3-512, Samsung 860 EVO 1 TB; ~1.82 TiB, 74% allocated | Striped without mirror/parity. A member failure threatens this pool; classify its current consumers before moving or repurposing any member. |
| boot-pool | T-FORCE 512 GB + HPE 480 GB mirror, ~222 GiB usable, 58% allocated | Mixed boot mirror with many boot environments. Current version reports `TrueNAS-26.0.0-MASTER+20260902-020152`; record the deliberate software release choice separately from hardware stability. |

`BigTank/k8s/rustfs` reports roughly 718 GiB used versus 292 GiB referenced. This
is ZFS accounting with snapshots/descendants, not evidence that 426 GiB is safe to
delete. Existing retired-name directories similarly need consumer and retention
checks before cleanup.

ARC was approximately **340 GiB** in a machine with **378 GiB visible RAM**. Linux
reported about 25 GiB available, no swap, and no current memory pressure. The
30-second ARC sample recorded 2,905 demand-data hits and zero demand-data misses.
Deduplication was off for the inspected Kubernetes datasets. That short, warm-cache
sample cannot establish a minimum RAM requirement or predict cold-cache behavior.

**Recommendation:** leave the NAS stable for this audit. If RAM/power reduction
becomes a separate project, use a reversible **128 GiB ARC cap as a first test
point**, not a claimed requirement; then consider 64 GiB only after observing a
representative backup, media and restore cycle. Compare client latency, backend
reads, demand-data miss rate, Kopiur backup/restore time and memory pressure against
baseline. Restore the previous cap if service latency or recovery time worsens.
Changing a cache cap is an experiment; removing physical DIMMs is a separate step.
No ARC cap was applied. TrueNAS describes memory sizing as workload dependent,
including shares, apps, VMs and caching; it does not establish this machine's
minimum from raw pool capacity alone. See the
[TrueNAS hardware guide](https://www.truenas.com/docs/scale/gettingstarted/scalehardwareguide/).

Home Assistant/Prometheus currently exposes actual plug measurements. One sample
showed Threadripper ~182 W, TrueNAS chassis ~114 W, separate NAS drive PSU ~43 W,
Elite ~33 W, SFF plus Dell ~63 W, and shed ~23 W. These are instantaneous readings,
not annual averages or guaranteed savings from a replacement. Use the existing
`docs/domains/power/metering.md` model for costs; separate gaming and office loads
from the homelab total. A future mini PC + 3090 may reduce host overhead, but its
power supply, GPU idle draw, eGPU link and passthrough support need their own design.

The local Deal Scout sourcing data was read from the sibling `deal-scout`
repository. Its older brief targets six independent SATA SSDs across three hosts,
while the owner now prefers approximately 480 GB and already owns three HPE
480 GB devices. Its dollar thresholds are operator buying criteria, not verified
current market offers. Buy against the revised placement plan, not the old quantity.

## Documentation and Mink inventory

| Source | Keep / correct |
| --- | --- |
| Root `CLAUDE.md`, nested directory rules | Strong operational guardrails and current GPU truth. Correct the globally strict AppSet wave claim and categorical RWO rollout wording; distinguish rules chosen for simplicity from Kubernetes semantics. |
| `docs/index.md` | Stale single-physical-host storage explanation and reversed llama.cpp/vLLM active state. This is especially harmful because it is the landing page. |
| `docs/easy-guide.md` | Useful learning structure. Reconcile current topology, counts and dependency ordering against the manifest graph; link rather than duplicate recovery steps. |
| `docs/storage-architecture.md` | Keep storage-tier and backup explanation. Separate established decisions, historical single-host constraints and the existing wired two-copy class. |
| `docs/disaster-recovery.md` | Substantial existing procedure, not a missing runbook. Keep terminal-Restore/reset and canary gotchas. Mark completed identity migrations historical; add app checks where "PVC restored" is insufficient. |
| `docs/domains/storage/` | Canonical Kopiur ownership, mover permissions and backup contract. Preserve these, especially per-PVC UIDs and restore-before-bind. |
| `docs/domains/scheduling/vpa-and-topology.md` | Reconcile old zone examples with physical zones hp-sff, hp-elite, dell, house and shed; retain per-container VPA boundaries. |
| `docs/domains/ai-gpu/` and `my-apps/ai/` | Canonical current model/backend and scale-swap behavior. Some telemetry/agent context still claims CNPG or vLLM as active; fix those consumers. |
| `docs/domains/power/metering.md`, HA configuration and dashboards | Current, useful evidence for hardware power decisions; recent PRs already improved these. |
| `omni/` templates, machine classes and provider examples | Describe declared provisioning. Pair with live inventory; do not infer physical RAM or active VM settings solely from class requests. |
| Mink project overview and task review | The April overview is historical and has later corrections. September task-review notes already distinguish completed/deferred items; preserve that classification. |

Relevant Mink records were reviewed, including:

- `projects/talos-argocd-proxmox/audit-closeout-pr-2236-and-deferred-app-overview.md`
- `projects/talos-argocd-proxmox/live-audit-root-refreshed-trivy-useful-gitea-replica-metadata-failure.md`
- `resources/cutover-lessons-2026-09-04-temporal-postgres-longhorn-wired-ha-pr-2220.md`
- `resources/post-nuke-all-gateways-dead-then-all-403-cilium-envoy-xds-mode-drift-split-xds-s.md`
- `resources/owner-confirmed-topology-and-operating-priorities-2026-09-05.md`

The vault had over 1,150 notes at initial inventory. This was a targeted review of
relevant project/current-incident records, not a claim to have revalidated every
note. Durable verified findings should link to dated evidence; old hypotheses and
superseded troubleshooting advice should stay labeled historical. In particular,
do not revive retired CNPG/VolSync/pvc-plumber paths or the superseded ADS rollback
suggestion from an earlier Cilium note.

Raw diagnostic files remain in the private local directory
`/tmp/talos-audit-20260905`. They are not committed as documentation. The repository
artifacts above preserve the reviewable conclusions and sanitized inventories.
