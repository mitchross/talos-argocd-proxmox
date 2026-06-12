# Longhorn V2 (SPDK) Engine — Tried and Retired

> **Status: RETIRED 2026-06-12.** The cluster runs Longhorn's **V1 engine**
> (the upstream default). This page is the record of why, and the conditions
> for ever trying V2 again. The full V2 build runbook and the day-by-day
> forensics live in git history (`docs/domains/storage/longhorn-v2-migration.md`,
> pruned 2026-06-13).

## What happened

The cluster was rebuilt onto the V2 (SPDK) data engine on 2026-06-11. Within
hours, the post-nuke mass restore (25 parallel VolSync restores + ~90 apps
attaching volumes) triggered a failure spiral the engine could not recover
from:

```
rebuild traffic → SPDK stalls → NVMe-TCP keep-alive timeouts
→ engine frontends die → volumes fault → MORE rebuilds → repeat
```

An instance-manager crash mid-storm left interrupted rebuilds everywhere;
those interrupted rebuilds **permanently corrupted replica metadata** on 10
freshly-restored volumes ("active chain parent … does not match head
parent"), and stale kernel NVMe-TCP state ultimately required a full host
reboot to clear. Every volume was recovered — the off-cluster Kopia repo +
restore-based DR carried the day — and the cluster returned to V1 the next
day (24/24 restored, unattended, ~75 minutes).

## Root causes

Matched **open Longhorn 1.12 bugs**, both targeting 1.13.0:

- [longhorn#13315](https://github.com/longhorn/longhorn/issues/13315) — an
  interrupted rebuild permanently poisons replica metadata
- [longhorn#13314](https://github.com/longhorn/longhorn/issues/13314) — a
  volume can crash again after automatic reattachment

Hardware amplified the trigger (consumer-SSD stripe shared by all workers,
CPU oversubscription starving SPDK's busy-poll reactors) but the defects are
upstream software — better hardware narrows the window, it does not fix the
metadata logic.

## Do not re-enable V2 without ALL of:

1. A Longhorn release with both bugs above **fixed and verified**.
2. A passed restore-canary DR drill *on V2* under mass-restore load.
3. Ideally: per-worker physical disks and non-oversubscribed CPU for the
   reactor cores.

## What V1 gives up vs what it bought

V2's latency/IOPS wins are irrelevant at this cluster's workload profile.
V1 is interrupt-driven (no ~5 busy-polled cores per node), tolerant of
shared homelab I/O, and boring under failure — the 2026-06-13 rebuild on V1
ran the identical restore wave without a single fault loop.
