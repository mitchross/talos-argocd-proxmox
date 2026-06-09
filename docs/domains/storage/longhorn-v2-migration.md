# Longhorn 1.12.0 — V2 (SPDK) Data Engine Migration Runbook

> **Status:** prep landed in GitOps; engine-enable + default-class cutover are
> manual, maintenance-window steps below. The cluster runs Longhorn **1.12.0**
> on the **V1** data engine today.
>
> **Scope decision (2026-06-09):** V2 on **all 4 storage nodes** (3 workers + 1
> GPU worker), operator provisions the block disks, and `longhorn-v2` becomes
> the **default** StorageClass at the end of the cutover.

## Why this is phased (read first)

Two facts force a manual, ordered rollout — they cannot be casual ArgoCD commits:

1. **Enabling `v2-data-engine` is blocked while any volume is attached.** Longhorn
   only applies the setting when **all** volumes are detached, and it restarts
   the instance-manager / CSI / engine-image pods when it does. If ArgoCD synced
   `v2DataEngine: true` while workloads ran, the setting would silently *not*
   apply and keep retrying. → engine-enable is a maintenance-window step.
2. **The default-class flip would break new-PVC provisioning** the instant it
   syncs if no node has a V2 block disk yet — every PVC that omits
   `storageClassName` would go `Pending` cluster-wide. → cutover is the *last*
   step, after disks are registered and validated.

## What already landed in Git (safe, no runtime change to V1)

| Change | File | Effect |
| --- | --- | --- |
| Removed invalid `guaranteedInstanceManagerMemory` no-op | `infrastructure/storage/longhorn/values.yaml` | None at runtime (was always ignored); fixes misleading config |
| Talos V2 prereqs (`vm.nr_hugepages=1024`, `nvme_tcp`+`vfio_pci`) on workers + gpu-worker | `omni/cluster-template/cluster-template.yaml` | None until `omnictl ... sync` + reboot |
| `longhorn-v2` StorageClass (non-default, `dataEngine: v2`) | `infrastructure/storage/longhorn/storageclass-v2.yaml` | Inert — provisions nothing until V2 is enabled + a disk exists |

## V1 vs V2 in 1.12.0 — what you keep / lose

Full parity for the things this repo depends on:

- ✅ **Snapshot, Backup & Restore, DR, System Backup** — all supported on V2, so
  the VolSync/Kopia + `driver.longhorn.io` VolumeSnapshotClass backup path works.
  **Still canary-validate it** (see Phase 4) before moving any backed-up PVC.
- ✅ Volume expansion, cloning, encryption, RWX (migratable), recurring jobs,
  online rebuilding, auto-balance, `best-effort` data locality.

Not supported on V2 in 1.12.0 — confirm nothing you migrate needs these:

- ❌ **Backing Image** (creation/backup) — replaced by CDI. Don't migrate any
  workload that depends on a Longhorn backing image.
- ❌ **strict-local** data locality (we use `best-effort`, fine).
- ❌ Offline fast rebuilding, orphaned-instance management, engine **live**
  upgrade (V2 volumes must be detached to upgrade 1.12.x patches).

---

## Phase 1 — Apply Talos prerequisites (per storage node, rolling)

The prereq patch is already in `cluster-template.yaml`. Apply and reboot:

```bash
# From the machine with omnictl + the cluster template:
omnictl cluster template sync -f omni/cluster-template/cluster-template.yaml

# Rolling reboot so hugepages + modules take effect. One node at a time;
# wait for Ready + Longhorn replicas to rebuild before the next.
# Do the GPU worker LAST and verify the GPU after it comes back.
talosctl reboot --nodes <worker-ip>
```

Verify on each storage node:

```bash
# 2 GiB of hugepages (1024 x 2Mi)
talosctl -n <node-ip> read /proc/meminfo | grep -i hugepages_total   # expect 1024
# modules loaded
talosctl -n <node-ip> read /proc/modules | grep -E 'nvme_tcp|vfio_pci'
```

On the **GPU worker** also confirm AI stack health:

```bash
kubectl -n llama-cpp get pods   # llama-cpp Running
kubectl -n comfyui  get pods    # comfyui Running
# (GPU still owned by nvidia.ko, not vfio)
```

## Phase 2 — Provision a raw block device per storage node

V2 needs a **raw block device** — it cannot reuse the filesystem-backed
`/var/lib/longhorn` (that stays V1). For each of the 4 storage VMs:

1. In **Proxmox**, add a second virtual disk to the worker VM on `ssdpool`
   (the GPU worker is on `ssdpool` too). Size to your V2 budget. Use a
   distinct controller/slot so it is easy to identify.
2. Do **not** create a Talos `UserVolumeConfig`/`VolumeConfig` for this disk and
   do not format it — Longhorn V2 claims the raw device directly. Talos leaves
   unreferenced disks untouched.
3. Find a **stable** path (device names like `/dev/sdb` are not stable across
   reboots — prefer `by-id`):

   ```bash
   talosctl -n <node-ip> ls -l /dev/disk/by-id/
   talosctl -n <node-ip> get disks        # Talos disk inventory
   ```

## Phase 3 — Maintenance window: enable the V2 engine

> Requires **all** volumes detached. Schedule downtime.

1. Scale every stateful workload to 0 (or cordon+drain) so Longhorn shows **no
   attached volumes**:

   ```bash
   kubectl get volumes -n longhorn-system   # Expect all 'detached'
   ```

2. Enable the engine in `values.yaml` and commit (let ArgoCD sync, or set the
   Setting CR directly during the window):

   ```yaml
   # infrastructure/storage/longhorn/values.yaml  ->  defaultSettings:
     v2DataEngine: true
   ```

   Longhorn restarts instance-manager / CSI / engine-image pods. Wait for
   `longhorn-system` to settle:

   ```bash
   kubectl -n longhorn-system get pods -w
   kubectl get settings.longhorn.io v2-data-engine -n longhorn-system -o jsonpath='{.value}'  # "true"
   ```

3. **Register the block disk on each node** (Longhorn owns the `Node` CR;
   add a `block`-type disk via UI or kubectl). UI: *Node → Edit Node and Disks
   → Add Disk → Type: Block, Path: `/dev/disk/by-id/<id>`*. Verify:

   ```bash
   kubectl -n longhorn-system get nodes.longhorn.io -o wide
   # each storage node should show a schedulable block disk, V2 engine Ready
   ```

4. Scale workloads back up; confirm V1 volumes reattach cleanly.

## Phase 4 — Canary-validate V2 (especially the backup path)

Before trusting V2 for anything backed up, prove the **VolSync/Kopia** flow end
to end on a throwaway PVC (this repo's backup contract is built around V1):

1. Create a small PVC with `storageClassName: longhorn-v2`, write data, confirm
   it provisions and attaches on SPDK (`kubectl get volumes -n longhorn-system`).
2. Add the pvc-plumber v4.0.1 backup labels (see `.claude/commands/add-backup.md`),
   then verify the in-namespace `volsync-kopia-repository` Secret + operator-owned
   `ReplicationSource`/`ReplicationDestination` appear and a backup completes:

   ```bash
   kubectl get secret,replicationsource,replicationdestination -n <canary-ns>
   ```
3. Confirm a CSI **VolumeSnapshot** is taken by the mover (the
   `driver.longhorn.io` VolumeSnapshotClass must work for V2) and that a restore
   into a fresh `longhorn-v2` PVC succeeds. **If any step fails, do NOT proceed
   to Phase 5** — keep V2 opt-in and leave V1 as default.

## Phase 5 — Cutover: make `longhorn-v2` the default

Only after Phase 4 passes. Two coordinated edits, one commit:

```yaml
# infrastructure/storage/longhorn/values.yaml -> persistence:
  defaultClass: false        # drops the default annotation from the V1 `longhorn` class
```

```yaml
# infrastructure/storage/longhorn/storageclass-v2.yaml -> metadata.annotations:
  storageclass.kubernetes.io/is-default-class: "true"   # uncomment this line
```

Verify exactly one default class:

```bash
kubectl get storageclass   # only longhorn-v2 should show (default)
```

Existing V1 volumes are untouched — they keep `storageClassName: longhorn`.
Only new PVCs that omit a class land on V2 from here.

## Rollback

- **Before Phase 5:** revert is trivial — V2 is opt-in, nothing defaults to it.
- **Undo default cutover:** set `persistence.defaultClass: true` and re-comment
  the `is-default-class` annotation; `longhorn` (V1) is default again.
- **Disable the engine:** detach all V2 volumes first (the setting is blocked
  otherwise), then set `v2DataEngine: false`. V1 is unaffected throughout.

## References

- Release notes: https://github.com/longhorn/longhorn/releases/tag/v1.12.0
- V1/V2 feature parity (1.12.0): https://longhorn.io/docs/1.12.0/v1-v2-volume-behavior-and-feature-parity/
- Talos support (hugepages + modules): https://longhorn.io/docs/1.12.0/advanced-resources/os-distro-specific/talos-linux-support/
- v2-data-engine setting (detach-to-change behavior): https://longhorn.io/docs/1.12.0/references/settings/
