# TrueNAS storage rules & NFS-stall troubleshooting

Rules for the `BigTank` NFS storage that backs cluster PVCs, and how to diagnose the
"everything on NFS times out and the box looks dead" failure.

## Rules

1. **Keep the TrueNAS System Dataset on `boot-pool`, never a data pool.** If
   `.system` sits on a data pool, a slow pool blocks `middlewared` → the API flaps →
   CSI reconnect storms → the box looks dead.
   Check: `midclt call systemdataset.config` → `pool` must be `boot-pool`.
2. **Don't set `special_small_blocks` on hot small-file datasets** (radar tiles, NVR
   clips) — it routes file data onto the metadata vdev, which chokes under small-file
   write load. Check: `zfs get -r special_small_blocks <pool>/k8s` → expect `0`.
3. **Don't build a metadata (special) vdev from consumer DRAM-less / no-PLP SSDs.**
   Under load they stall (ZFS `class=delay` up to ~55s) and block NFS metadata. A
   3-way mirror doesn't help — that's redundancy, not sync-write speed. Use
   enterprise PLP SSDs, or no special vdev.

## Symptoms of a special-vdev stall
- App requests time out (~55s); in-memory endpoints (`/healthz`) stay fine.
- `middlewared` API (:443) flaps; NFS mounts time out, existing `hard` mounts hang.

## Fixes

Stop routing file data to the special vdev:
```bash
zfs set special_small_blocks=0 BigTank/k8s
zfs set special_small_blocks=0 BigTank/k8s/frigate
zfs set special_small_blocks=0 BigTank/k8s/kiwix
zfs get -r -s local special_small_blocks BigTank/k8s   # only =0 should remain
```

Keep the System Dataset off the data pool:
```bash
midclt call systemdataset.config
midclt call systemdataset.update '{"pool":"boot-pool"}'
```

Remove a stalling special mirror (safe only when the pool is all mirrors, no raidz;
ZFS evacuates metadata to the HDDs and the pool stays online):
```bash
# Pool healthy, NOT mid-stall
zpool status -v BigTank                     # all ONLINE, confirm NO raidz
kubectl -n radar-ng scale deploy --all --replicas=0   # drop NFS load; pause Argo selfHeal
zpool remove BigTank <special-mirror-id>    # verify the id is under `special`, not a data mirror
zpool status BigTank                         # "remove: in progress" — slow, let it finish
```
Metadata then lives on the HDDs (slower lookups, no stall). It's one-way — you can't
cleanly re-add metadata to an indirect-mapped pool.

## Diagnostic commands
```bash
zpool events BigTank | grep class=delay          # the stall signature (healthy = 0)
zfs get -r special_small_blocks BigTank/k8s      # expect 0 everywhere
zpool iostat -vl BigTank 5                        # special-vdev latency (µs healthy)
midclt call systemdataset.config                  # System Dataset pool placement
```

## Environment
- BigTank: HGST 10 TB HDD mirrors. storageClass `truenas-nfs` / `csi.truenas.io`,
  mountOptions `hard,nfsvers=4.1,nconnect=16`. `BigTank/k8s`: recordsize 128K,
  `sync=disabled`, zstd, atime off.
- ARC is not capped; a low idle ARC reading (~5 GiB on a 157 GiB box) is normal.

## Related
- [storage-architecture.md](storage-architecture.md)
- [disaster-recovery.md](disaster-recovery.md)
