# Runbook: TrueNAS special-vdev stall → NFS timeouts → cluster outage

**Incident date:** 2026-06-14 · **Affected:** radar-ng (and any NFS consumer of BigTank) · **Resolution:** software-only, no hardware change.

> ⚠️ **UPDATE — this recurred on 2026-06-16/17. The software-only fix was insufficient.** The special vdev (consumer SSDs) was the real root cause and was never replaced. See **[Recurrence 2026-06-16](#recurrence-2026-06-16--software-fix-was-insufficient-vdev-removed)** below. Permanent fix: the metadata mirror was **removed** from the pool (`zpool remove`), evacuating metadata to the HDDs. The "Preventive followup (not urgent)" at the bottom is now **done, and was never optional.**

This documents a multi-layer outage where the radar-ng app went dark, the TrueNAS box hung/flapped, and the cluster hit `ImagePullBackOff`. All three root causes were **runtime TrueNAS/DNS config, not GitOps manifests** — so there is nothing in this repo that "caused" it, but the operational lessons below must be honored when standing up clusters or TrueNAS datasets.

## TL;DR — the three durable rules

1. **TrueNAS System Dataset must live on `boot-pool`, never a data pool.** If `.system` is on a data pool (e.g. BigTank), a slow/stalling pool blocks `middlewared` → the API flaps → CSI reconnect storms → the box looks dead. Check: `midclt call systemdataset.config` → `pool` must be `boot-pool`.
2. **Never set `special_small_blocks` on hot small-file datasets** (radar tiles, NVR clips) backed by a consumer-SSD special vdev. It routes file *data* — not just metadata — onto the SSDs, which then choke under small-file write load. Check: `zfs get -r special_small_blocks <pool>/k8s` → expect `0` everywhere.
3. **After a DNS migration (Technitium), expect stale resolver cache.** Internal names can resolve to old IPs (e.g. `registry.vanillax.me` → the Omni host, giving a TLS "valid for omni.vanillax.me" error). external-dns/HTTPRoute are usually already correct; the fix is cache expiry, not a manifest change. Verify source of truth with `dig +short <name> @<technitium-ip>` vs the default resolver.

## Symptoms
- App tiles time out (~55s); static/in-memory endpoints (`/healthz`, style JSON, forecast) stay fine.
- `middlewared` API (:443) flaps (`connection refused` → recover → repeat).
- NFS mounts time out (`mount timed out after 1m50s`); existing `hard` mounts hang. `showmount`/rpcbind still answer.
- iLO console floods with `systemd-journald@netdata` leaked-process storm + "system.journal corrupted/uncleanly shut down" (a *symptom* of hard-resetting the hung box, not the cause).
- Cluster-wide `ImagePullBackOff` (registry DNS, separate issue surfaced during recovery).

## Root cause 1 — special-vdev stall (primary)
`BigTank/k8s` had `special_small_blocks=64K` (children `frigate=16K`, `kiwix=64K` as *local* overrides); recordsize 128K. This routed all file data ≤ threshold onto the **special (metadata) vdev** — a 3-way mirror of consumer DRAM-less T-FORCE 512G SATA SSDs (no PLP). Under the cluster's small-file write firehose (`nconnect=16` over 10GbE) the SSDs stalled, logging ZFS `class=delay` up to **55,000 ms**, which blocked NFS metadata (getattr/lookup).

fio (4k randwrite, fdatasync): special vdev only ~1720 sync IOPS / 37ms avg / 203ms max (enterprise PLP NVMe = 50–200k IOPS, sub-ms).

**Fix**
```bash
zfs set special_small_blocks=0 BigTank/k8s
zfs set special_small_blocks=0 BigTank/k8s/frigate
zfs set special_small_blocks=0 BigTank/k8s/kiwix
zfs get -r -s local special_small_blocks BigTank/k8s   # verify: only =0 remain
```
Data now goes to the HDD mirrors; metadata stays on the special SSD. Only affects *new* writes — the special vdev (~340G/472G, 72%) drains over days as tiles/clips churn. The democratic-csi provisioner does **not** stamp `special_small_blocks`, so PVC children inherit `0` — the fix sticks.

## Root cause 2 — System Dataset on BigTank (control-plane coupling)
`.system` was on BigTank. When BigTank stalled, `.system` blocked → `middlewared` stalled → :443 dropped → democratic-csi (`csi.truenas.io`) reconnected in a tight loop (controller crash-looped, 71 restarts) → box appeared dead → hard-reset → unclean shutdown corrupted boot-pool journals → `systemd-journald@netdata` crash-loop/leak storm on reboot.

**Fix**
```bash
midclt call systemdataset.config                       # confirm pool
midclt call systemdataset.update '{"pool":"boot-pool"}' # decouple from data pool
```
No service flap during migration (`middlewared` NRestarts stayed 0). Journals were on boot-pool, not BigTank; `journalctl --verify` PASS.

## Root cause 3 — registry ImagePullBackOff (stale DNS)
After the Technitium migration, `registry.vanillax.me` resolved to stale `192.168.10.15` (Omni) instead of `192.168.10.52`, so pulls failed TLS ("certificate is valid for omni.vanillax.me"). external-dns + HTTPRoute were already correct (Technitium had `→ 192.168.10.52`, TXT-owned). Stale resolver cache; self-resolved on expiry. No repo change needed.

## Recurrence 2026-06-16 — software fix was insufficient, vdev removed
**Box stayed stable a few days, then hard-locked again** (iLO console = same `systemd-journald` corruption/SIGKILL storm). Same box (`192.168.10.133`; `.182` is its iLO/BMC), same `BigTank`, same special mirror.

**Why the 2026-06-14 fix didn't hold:** `special_small_blocks=0` only stops *new file data* from routing to the special vdev. **All pool metadata still mandatorily lives there**, so every lookup/getattr/txg-metadata-write still funnels through the consumer SSDs. The software fix lowered load below the stall threshold for a few days; any load spike (firehose, scrub, snapshot) pushed it back over.

**Why "I have 3 of them" doesn't save you:** the 3-way mirror buys *redundancy*, not *speed*. Every write commits to all three drives and isn't done until the **slowest** acknowledges — so three consumer SSDs write as slow as one (slightly slower). Mirror width = number of copies, not throughput. The stall is a per-drive sync-write-latency problem (T-FORCE = DRAM-less, no PLP: ~1,720 sync IOPS, 203ms max) that mirroring cannot fix.

**Permanent fix applied — `zpool remove` of the metadata mirror.** Safe here because BigTank is **all mirrors, no raidz** (top-level vdev removal is only supported without raidz). This is an *evacuation*, not a loss: ZFS copies all metadata off the special vdev onto the HDDs, builds an indirect map, then detaches the empty vdev — pool stays online throughout. (Drive *failure* of the special vdev = whole-pool loss; a planned `zpool remove` = pool survives. Different events — don't conflate them.)

```bash
# Pre-flight (box recovered, healthy, NOT mid-stall)
zpool status -v BigTank                       # all ONLINE, confirm NO raidz
zpool events BigTank | grep -c class=delay    # not climbing
midclt call systemdataset.config              # still boot-pool (root-cause-2 guard)
# Take cluster load off so SSDs serve ONLY the evacuation copy
kubectl -n radar-ng scale deploy --all --replicas=0   # + other BigTank NFS writers; pause Argo selfHeal
zpool iostat -vl BigTank 5                     # confirm special-vdev writes drop to idle
# Remove the SPECIAL mirror (verify the id is under `special`, NOT a data mirror)
zpool remove BigTank <special-mirror-id>
zpool status BigTank                           # shows "remove: in progress" %/ETA; reads come off the
                                               # choking SSDs so it's slow — let it finish
# After: special vdev gone, small permanent `indirect-*` mapping in RAM. Restore apps/Argo.
```
**Trade-off accepted:** metadata now on HDD (slower lookups than a *good* SSD, but HDDs don't stall the way the consumer SSDs did). One-way: can't cleanly re-add the same metadata to the indirect-mapped pool later. The keep-fast-metadata alternative was a one-at-a-time **Replace** of the 3 SSDs with enterprise PLP drives — not chosen (free path preferred).

## Diagnostic commands
```bash
zpool events BigTank | grep class=delay          # the 55s-stall signature (healthy = 0)
zfs get -r special_small_blocks BigTank/k8s      # expect 0 everywhere
zpool iostat -vl BigTank 5                        # special-vdev latency (µs healthy)
zpool list -v BigTank                             # special vdev alloc/cap
midclt call systemdataset.config                  # System Dataset pool placement
dig +short registry.vanillax.me @192.168.10.15    # DNS source of truth vs default resolver
kubectl describe pod <pod>                         # image-pull TLS error
```

## Environment facts (as of incident)
- Gateways (Cilium): external `192.168.10.33`, internal `192.168.10.50`, **internal-technitium `192.168.10.52`**.
- external-dns-technitium: `--source=gateway-httproute --gateway-label-filter=external-dns-gateway=gateway-internal-technitium --provider=rfc2136 --policy=upsert-only --txt-owner-id=talos-prod-technitium --domain-filter=vanillax.me`.
- Technitium DNS at `192.168.10.15` (same host as Sidero Omni; Omni K8s proxy `omni.vanillax.me:8100`).
- BigTank: mirror HGST 10TB HDDs + special mirror = 3× T-FORCE 512G consumer SATA SSD. storageClass `truenas-nfs` / `csi.truenas.io`, datasetPath `k8s/nfs/v`, mountOptions `hard,nfsvers=4.1,nconnect=16`. `BigTank/k8s`: recordsize 128K, `sync=disabled`, zstd, atime off.
- ARC is **not** capped: on a 157GiB box it idles at ~5GiB (c_min = RAM/32) and scales to tens of GiB under load (`arc_c_max`=156GiB, `zfs_arc_max`=0). A low idle ARC reading is normal, not a bug.

## Hardware followup — DONE 2026-06-17 (was NOT optional)
**Originally filed as "not urgent." The 2026-06-16 recurrence proved it was the actual root cause.** Resolved by **removing** the special vdev entirely (`zpool remove`, metadata evacuated to HDD) — see [Recurrence 2026-06-16](#recurrence-2026-06-16--software-fix-was-insufficient-vdev-removed). The alternative (never used) was to replace the consumer SSDs with enterprise PLP SSDs (Solidigm/Intel S-series, Samsung PM), keeping the 3-way mirror intact during the swap — **special-vdev loss = whole-pool loss** — after verifying a current BigTank backup. **Lesson: a metadata vdev built from consumer DRAM-less/no-PLP SSDs is a latent outage, not a perf tweak. Don't ship one.**

## Related
- [storage-architecture.md](storage-architecture.md)
- [disaster-recovery.md](disaster-recovery.md)
