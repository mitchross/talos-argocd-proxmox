# Control plane: 1 to 3 members

Trial, tracked in #3071 step 4. If it hurts, go back to 1 (see Rollback).

## Layout

| Member | Host | Schedulable |
|---|---|---|
| hp-sff CP VM (`.94`) | Proxmox on hp-sff | No (keeps `NoSchedule`) |
| `hp-elite-gen12` (`.82`) | bare metal, 16 GB | Yes |
| `mini-pc-dell-ultra-worker` (`.181`) | bare metal, 32 GB | Yes |

The `ControlPlane` set lists the three machines by UUID (a set takes machines or a class, not both). The two minis were worker sets; their labels, kubelet, watchdog, Longhorn disk and extension settings now live in their `kind: Machine` documents. Schedulable control planes use a per-machine `allowSchedulingOnControlPlanes: true`. Their kubelet reserves 2 GiB / 1 GiB memory for etcd and the API server. KubePrism (`localhost:7445`) already gives every node API failover, so Cilium needs no change.

Neither mini holds a Longhorn replica today, so resetting them loses no volume data.

## Before you sync

0. The Pi (Omni) stays a single point of failure for management: three control planes keep the cluster running, not reachable. While it is healthy, export direct credentials (check `omnictl kubeconfig --help` and `omnictl talosconfig --help` for the break-glass flag) and keep them offline, and copy the Omni state backup off the Pi.
1. Snapshot etcd and copy it off the node: `talosctl -n 192.168.10.94 etcd snapshot /tmp/etcd-pre-3cp.db`.
2. Expect downtime while each mini is reset and rejoins: Home Assistant and Zigbee on `hp-elite-gen12`, Frigate on the Dell. Pick a quiet hour.
3. From the main checkout (the `docker-hub-auth` patch is gitignored): `git pull`, then
   `omnictl cluster template diff -f omni/cluster-template/cluster-template-prod-v2.yaml`.
   Accept only if the VM stays in the control-plane set and the two minis move from worker sets to it. Check the diff that each mini's extensions come out as its `kind: Machine` list. Omni's merge of per-machine and per-set extensions is not documented; the diff is the proof.
4. `omnictl cluster template sync -f ...`, then watch `omnictl get clustermachinestatus` and `talosctl etcd members` (expect 3).

## Measure

Take a baseline before the sync and compare after one day. The etcd 99th-percentile fsync is the number that decides it.

| Check | Query | Want |
|---|---|---|
| WAL fsync p99 | `histogram_quantile(0.99, sum by (le,instance) (rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m])))` | under 25 ms |
| Backend commit p99 | `histogram_quantile(0.99, sum by (le,instance) (rate(etcd_disk_backend_commit_duration_seconds_bucket[5m])))` | under 100 ms |
| Leader changes | `increase(etcd_server_leader_changes_seen_total[1d])` | 0 to 1 |
| Failed proposals | `increase(etcd_server_proposals_failed_total[1d])` | 0 |
| API latency | the "WHY IS THIS APP SLOW?" and cluster cockpit dashboards | no step change |
| Disk | `node_disk_io_time_seconds_total` on the minis' system disk | not saturated |

Thrashed disk means fsync p99 over 100 ms sustained, or repeated leader changes.

## Rollback to 1 control plane

Revert this PR, `git pull`, diff, sync. Omni removes the two minis from etcd, wipes them, and they rejoin as workers from the restored worker sets. Do not do this while the VM member is unhealthy; restore from the snapshot only if quorum is lost (`docs/disaster-recovery.md`).

## Rules

- Keep an odd member count.
- Do not add control planes to repair a lost quorum.
- Run Longhorn replicas on the minis only on a disk that is not the etcd disk.
