# TrueNAS special-vdev stall runbook

This runbook covers one failure: every app on NAS storage times out and the TrueNAS box
looks dead. It gives three rules that prevent the failure, the commands that confirm it,
and the fixes. The fixes change ZFS properties and the pool layout on the NAS. They change
nothing in Kubernetes except one optional scale-down.

A special vdev is a set of SSDs in a ZFS pool that holds the pool's metadata, and
optionally small files. When those SSDs stall, every NFS metadata request waits for them.

## The NAS storage this covers

- BigTank is the pool of HGST 10 TB HDD mirrors.
- The `truenas-nfs` StorageClass (`csi.truenas.io`) mounts with
  `hard,nfsvers=4.1,tcp,rsize=1048576,wsize=1048576,noatime,nconnect=16`.
- `BigTank/k8s` uses recordsize 128K, `sync=disabled`, zstd compression and atime off.
- ARC, the ZFS RAM cache, has no size cap. A low idle ARC reading (about 5 GiB on a
  157 GiB box) is normal.

## Rules that prevent the stall

1. Keep the TrueNAS System Dataset on `boot-pool`, never on a data pool. If `.system` is
   on a data pool, a slow pool blocks `middlewared`, the TrueNAS API service. The API then
   goes up and down, the CSI driver reconnects again and again, and the box looks dead.
   Check with `midclt call systemdataset.config`. The `pool` field must be `boot-pool`.
2. Do not set `special_small_blocks` on datasets that write many small files, such as
   radar tiles or NVR clips. The property sends file data to the metadata vdev, and that
   vdev stalls under small-file writes. Check with
   `zfs get -r special_small_blocks <pool>/k8s`. Expect `0`.
3. Do not build a special vdev from consumer SSDs that have no DRAM or no power-loss
   protection (PLP). Under load they stall, and ZFS records `class=delay` events of up to
   about 55 s. A 3-way mirror does not help, because it adds redundancy, not sync-write
   speed. Use enterprise PLP SSDs, or use no special vdev.

## Symptoms

- App requests time out after about 55 s. Endpoints that answer from memory, such as
  `/healthz`, stay healthy.
- The `middlewared` API on port 443 goes up and down.
- New NFS mounts time out, and existing `hard` mounts hang.

## Before you start

Run the diagnostic commands on the NAS. They only read.

```bash
zpool events BigTank | grep class=delay          # the stall signature (healthy = 0)
zfs get -r special_small_blocks BigTank/k8s      # expect 0 everywhere
zpool iostat -vl BigTank 5                        # special-vdev latency (µs healthy)
midclt call systemdataset.config                  # System Dataset pool placement
```

A healthy pool shows no `class=delay` events and special-vdev latency in microseconds.
Then apply the fix that matches what you found.

## Fix 1: stop sending file data to the special vdev

```bash
zfs set special_small_blocks=0 BigTank/k8s
zfs set special_small_blocks=0 BigTank/k8s/frigate
zfs set special_small_blocks=0 BigTank/k8s/kiwix
zfs get -r -s local special_small_blocks BigTank/k8s   # only =0 should remain
```

Expect the last command to list only values of `0`.

## Fix 2: move the System Dataset to the boot pool

```bash
midclt call systemdataset.config
midclt call systemdataset.update '{"pool":"boot-pool"}'
```

Expect `boot-pool` in the `pool` field when you run the first command again.

## Fix 3: remove a special mirror that stalls

!!! warning
    This change cannot be reversed. After the removal, ZFS maps the moved metadata
    indirectly, and you cannot cleanly add a special vdev back to that pool. Remove the
    mirror only when every vdev in the pool is a mirror. The removal is not safe on a
    pool that has a raidz vdev.

Do this while the pool is healthy, not during a stall. ZFS moves the metadata to the HDDs,
and the pool stays online.

```bash
# Pool healthy, NOT mid-stall
zpool status -v BigTank                     # all ONLINE, confirm NO raidz
kubectl -n radar-ng scale deploy --all --replicas=0   # drop NFS load; pause Argo selfHeal
zpool remove BigTank <special-mirror-id>    # verify the id is under `special`, not a data mirror
zpool status BigTank                         # "remove: in progress" — slow, let it finish
```

Expect `zpool status` to show `remove: in progress`. The removal is slow. Let it finish.
Afterward the metadata lives on the HDDs, so lookups are slower but they do not stall.

## Roll back

Fix 1 and fix 2 change one property each. To undo one, set the property back to the value
it had, but the rules above say to keep the fixed values. Fix 3 has no rollback. After the
removal finishes, scale the `radar-ng` Deployments back up and resume Argo CD self-heal if
you paused it.

## Related

- [Storage architecture](storage-architecture.md)
- [NAS performance and RAM](nas-performance.md)
- [Disaster recovery](disaster-recovery.md)
