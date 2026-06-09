# Longhorn 1.12.0 — V2 (SPDK) Data Engine Migration Runbook

> **Status:** prep landed in GitOps; engine-enable + default-class cutover are
> manual, maintenance-window steps below. The cluster runs Longhorn **1.12.0**
> on the **V1** data engine today.
>
> **Scope decision (2026-06-09):** V2 on **all 4 storage nodes** (3 workers + 1
> GPU worker), and `longhorn-v2` becomes the **default** StorageClass.
> **Rollout chosen: nuke & rebuild** (clean slate) — not an in-place migration.
> Disk: the existing single ~800G worker disk is **split** into a system disk +
> a dedicated raw V2 block device via the provider's `additional_disks` (same
> total capacity), wired into the machine classes.

## Chosen path: nuke & rebuild (do this)

Because the cluster is being rebuilt from scratch, most of the in-place hazards
below evaporate — there are no attached volumes to block the engine-enable, and
the disks exist from first boot. Order of operations:

1. **Machine classes already carry the layout** (`omni/machine-classes/worker.yaml`
   + `gpu-worker.yaml`): `disk_size` shrunk to the system disk (100G workers /
   150G GPU) plus an `additional_disks` raw block device on `ssdpool` for V2
   (700G / 650G). On a fresh provision these attach as `scsi0` → `/dev/sda`
   (Talos system + V1) and `scsi1` → `/dev/sdb` (raw, for V2).
2. **Cluster template already carries the V2 prereqs** (hugepages + `nvme_tcp` +
   `vfio_pci` on workers + gpu-worker). They take effect on first boot.
3. **Provider digest supports `additional_disks`** — confirmed for the pinned
   `2026-05-23` digest in `omni/proxmox-provider/docker-compose.yml` (upstream
   multi-disk config predates it; verified against `internal/pkg/provider/data.go`
   and the provider's multi-disk docs). Per-disk `storage_selector` / `disk_ssd`
   / `disk_discard` are honored. If you ever roll the pin *back* before mid-April
   2026, re-verify — the field is silently ignored on builds that lack it.
4. Provision the cluster. After Longhorn comes up, **register the `/dev/sdb`
   block disk on each storage node by its `by-id` path** (Phase 3 step 3) — this
   is the one post-bootstrap manual step.
5. **Enable V2 from the start** — on a fresh cluster there are no attached
   volumes, so set `v2DataEngine: true` (Phase 3 step 2) without a maintenance
   window.
6. **Canary-validate the VolSync/Kopia backup path on V2** (Phase 4) before
   making it default.
7. **Make `longhorn-v2` the default** (Phase 5). Keep V1 as default until the V2
   disks are registered and the canary passes, so bootstrap PVCs don't hang.

The phased detail below still applies for each step; the only thing the rebuild
removes is the detach-everything maintenance window for the engine-enable.

## Why the in-place path is phased (reference)

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
`/var/lib/longhorn` (that stays V1). Do **not** create a Talos
`UserVolumeConfig`/`VolumeConfig` for this disk and do not format it — Longhorn
V2 claims the raw device directly, and Talos leaves unreferenced disks untouched
(the install/system disk is pinned to `/dev/sda`). The new disk attaches as
`scsi1` → `/dev/sdb` in the guest.

### Preferred: declarative via the Omni Proxmox provider (`additional_disks`)

The `siderolabs/omni-infra-provider-proxmox` provider supports
`additional_disks` (verified in `internal/pkg/provider/data.go` — the older
"single disk per VM" note in `omni/machine-classes/*.yaml` is stale). Add this to
the `providerData` of `omni/machine-classes/worker.yaml` **and**
`omni/machine-classes/gpu-worker.yaml`:

```yaml
      additional_disks:
        - storage_selector: name == "ssdpool"
          disk_size: 200          # V2 capacity budget, GB — set to taste
          disk_ssd: true
          disk_discard: true
          disk_iothread: true
          disk_cache: none
          disk_aio: io_uring
```

Caveats:
- **Applies at VM provisioning, not as a hot-add.** Editing the machine class
  does not grow already-running VMs. Either reprovision each node rolling
  through Omni (the VM is recreated empty — safe here: V1 is replica-2 + VolSync
  backs up everything, replicas rebuild), or hot-add once in Proxmox
  (`qm set <vmid> -scsi1 ssdpool:200,ssd=1,discard=on,iothread=1,cache=none,aio=io_uring`)
  and keep the machine-class entry so future reprovisions stay consistent. Test
  on one canary worker first.
- **Confirm the pinned provider digest includes the feature.** The provider is
  pinned by content digest in `omni/proxmox-provider/docker-compose.yml`; if the
  pinned build predates `additional_disks` it is silently ignored — bump the
  digest (lookup command is in that compose file) if so.

### Alternative: add the disk manually in Proxmox

Add a second virtual disk to each worker VM on `ssdpool` via the Proxmox UI /
`qm set`. Functionally identical from the guest's side; just not declarative.

### Then: find the stable device path for Longhorn registration

`/dev/sdb` is **not** stable across reboots — register the V2 disk in Longhorn
by its `by-id` path (Phase 3, step 3):

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
