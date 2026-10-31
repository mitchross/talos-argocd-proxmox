# Prometheus series trim

Goal: drop series nothing reads, keep dashboards/alerts intact, show evidence.

1. Live head stats: `/api/v1/status/tsdb?limit=60`; per-job per-name counts: `count by (job,__name__)({__name__=~".+"})` (about 20k rows, fine with `curl -m 200`).
2. Referenced set = every identifier in `expr`/`query`/`definition` of all repo dashboard JSONs (walk nested dicts) plus every live rule from `/api/v1/rules`. Check whether chart default dashboards are enabled (`defaultDashboardsEnabled`); if off, repo dashboards are the full set.
3. Unreferenced = live names not in that set (a `_bucket/_sum/_count` is referenced if any sibling is).
4. Prefer dropping only `_bucket` series (keeps `_sum/_count` averages) plus clearly unused state families; keep owner metrics, memory usage, network errors for ad-hoc debugging.
5. Simulate the final regexes against the per-name counts, assert zero referenced names are dropped, and report series saved per source.
6. Cannot render helm in the pod: say CI renders it, and give the before/after check (`prometheus_tsdb_head_series`).

# HA for single-writer apps (e.g. SQLite-backed agents)
- Run 1 replica, `Recreate`, on Longhorn RWO with 2 replicas; do not use NFS/SMB (SQLite locking, NAS becomes SPOF).
- Cut node-loss wait with `not-ready`/`unreachable` tolerations (30 s); Longhorn `node-down-pod-deletion-policy` handles detach.

# Control-plane placement
- Spread the 3 members over 3 physical hosts; two VMs on one Proxmox host share a failure domain, so that host loss costs quorum. A worker VM on the same host as a CP VM does not count as a third member.
- Prefer members with RAM headroom (check live allocatable, minus planned kubelet reservations) and avoid ones running latency-sensitive hardware workloads (NPU/Frigate) when an equal alternative exists.
- A host that is down cannot yet host a VM member; sync the reachable 3 first, then do 3 -> 4 -> 3 later so the member count stays odd except transiently.

# Control-plane trial measurements
etcd WAL fsync p99 < 25 ms, backend commit p99 < 100 ms, leader changes 0-1/day, failed proposals 0. Always give a rollback (revert PR + sync) and snapshot etcd first.
