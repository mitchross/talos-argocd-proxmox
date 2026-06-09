# Longhorn 1.12.0 — V2 (SPDK) Data Engine Rebuild Runbook

> **Status:** the rebuild target config is fully in GitOps. This cluster is
> **V2-only**: `v2DataEngine: "true"`, `v1DataEngine: "false"`, and the default
> `longhorn` StorageClass routed to the V2 engine via `persistence.dataEngine: v2`.
> All of it applies when the **rebuilt** cluster bootstraps.
>
> **Scope decision (2026-06-09):** nuke & rebuild (clean slate), **V2-only** — no
> V1 volumes to migrate, so the V1 engine is disabled outright. V2 runs on
> **all 4 storage nodes** (3 workers + 1 GPU). Each node's single ~800G disk is
> **split** (same total) into an OS disk + a dedicated raw V2 block device via
> the provider's `additional_disks`: workers **96G OS / 704G V2**, GPU worker
> **128G OS / 672G V2** (OS disks sized to absorb committed pod
> `ephemeral-storage` *limits* + container images — see the machine-class
> comments for the math).
>
> **Key design choice — the StorageClass keeps the name `longhorn`.** 40+ PVCs,
> the inline VolSync ReplicationSource/Destination configs, the pvc-plumber
> backup contract, and the CLAUDE.md / `/add-backup` guidance all say
> `storageClassName: longhorn` explicitly. Re-pointing that NAME at the V2
> engine (chart value `persistence.dataEngine: v2`) moves all of them at once;
> a separate `longhorn-v2` class + default-flip would have moved **none** of
> them (default-class only affects PVCs that omit `storageClassName`). The
> earlier `storageclass-v2.yaml` has been deleted.
>
> ⚠️ **Sync timing:** this branch must **not** sync onto the still-running V1
> cluster — the engine flips can't apply while volumes are attached (silent
> retry churn) and the `longhorn`-class re-route would send every new PVC to a
> V2 engine with no disks (Pending cluster-wide). Land it only as the rebuilt
> cluster comes up. The disk split needs a reprovision anyway — the provider
> does not hot-resize.

## Why V2-only (no V1)

V1 only mattered for an *in-place* migration: you cannot hot-convert V1 volumes
to V2, so a live cutover runs both engines side-by-side while data moves. A nuke
& rebuild deletes all volumes, so there is nothing to migrate — every PVC is
created fresh on V2. In 1.12.0 V2 has parity for everything this repo uses
(snapshots, backup/restore, DR, expansion, clone, encryption, RWX-migratable,
recurring jobs). With `v1DataEngine: "false"`, anything that somehow requests a
V1 volume fails **loudly** at provision time instead of silently binding to the
small OS disk. The **one** thing to prove is the repo's backup/DR plumbing
(VolSync/Kopia + `driver.longhorn.io` VolumeSnapshotClass), which was built on
V1 — see the backup canary (Phase 4).

## Rebuild order of operations (do this)

1. **Machine classes already carry the disk layout**
   (`omni/machine-classes/worker.yaml` + `gpu-worker.yaml`): OS disk
   (96G workers / 128G GPU) plus an `additional_disks` raw block device on
   `ssdpool` for V2 (704G / 672G). On a fresh provision these attach as
   `scsi0` → `/dev/sda` (Talos + images + pod ephemeral) and `scsi1` →
   `/dev/sdb` (raw, for V2).
2. **Cluster template already carries the V2 kernel prereqs** (hugepages →
   2 GiB + `nvme_tcp` + `vfio_pci` on workers + gpu-worker); they take effect on
   first boot. **Longhorn values already carry the engine + class config**:
   `v2DataEngine: "true"`, `v1DataEngine: "false"`,
   `createDefaultDiskLabeledNodes: "true"` (no auto-created filesystem disk on
   the OS partition), and `persistence.dataEngine: v2` on the default
   `longhorn` class. All quoted strings — bare YAML bools have caused
   `strconv.Parse*` failures in longhorn-manager before.
3. **Provider digest supports `additional_disks`** — confirmed for the pinned
   `2026-05-23` digest in `omni/proxmox-provider/docker-compose.yml` (upstream
   multi-disk config predates it; verified against `internal/pkg/provider/data.go`
   and the provider's multi-disk docs). Per-disk `storage_selector` / `disk_ssd`
   / `disk_discard` are honored. If you ever roll the pin *back* before mid-April
   2026, re-verify — the field is silently ignored on builds that lack it.
4. Provision the cluster. **Register the `/dev/sdb` block disk on each storage
   node by its `by-id` path** (Phase 3) as soon as Longhorn is healthy and
   **before** the heavy app waves (monitoring/my-apps). This is the one
   post-bootstrap manual step. It is **not** a Talos mount — the disk stays raw
   and is added as a Longhorn **block-type** disk on the Node CR. Until it's
   registered there is **zero** Longhorn capacity (default-disk auto-creation is
   off) and `longhorn`-class PVCs sit `Pending` — no data loss, they bind once
   the disk appears.
5. **Canary-validate the VolSync/Kopia backup path on V2** (Phase 4) before
   trusting real data to it — this is the gate, not optional, since the backup
   contract was V1-built.

## What is in Git (applies at rebuilt-cluster bootstrap)

| Change | File |
| --- | --- |
| V2 engine on, V1 engine off, no auto default disks (all quoted strings) | `infrastructure/storage/longhorn/values.yaml` `defaultSettings` |
| Default `longhorn` class routed to V2 (`persistence.dataEngine: v2`, `defaultClass: true`) — class name unchanged on purpose | `infrastructure/storage/longhorn/values.yaml` `persistence` |
| ~~Separate `longhorn-v2` StorageClass~~ **deleted** — superseded by the above | (removed) `infrastructure/storage/longhorn/storageclass-v2.yaml` |
| Talos V2 prereqs (`vm.nr_hugepages=1024`, `nvme_tcp`+`vfio_pci`) on workers + gpu-worker | `omni/cluster-template/cluster-template.yaml` |
| Disk split: 96G/704G workers, 128G/672G GPU via `additional_disks` | `omni/machine-classes/{worker,gpu-worker}.yaml` |

> Chart quirk worth knowing: the Longhorn 1.12.0 chart only renders the
> `dataEngine` StorageClass parameter when `persistence.disableRevisionCounter`
> is truthy. It defaults to `"true"` — do **not** override it to false/empty or
> the `longhorn` class silently reverts to V1.

## V1 vs V2 in 1.12.0 — what you keep / lose

Full parity for the things this repo depends on:

- ✅ **Snapshot, Backup & Restore, DR, System Backup** — all supported on V2, so
  the VolSync/Kopia + `driver.longhorn.io` VolumeSnapshotClass backup path works.
  **Still canary-validate it** (Phase 4) before trusting backed-up data to it.
- ✅ Volume expansion, cloning, encryption, RWX (migratable), recurring jobs,
  online rebuilding, auto-balance, `best-effort` data locality.

Not supported on V2 in 1.12.0 — confirm nothing you deploy needs these:

- ❌ **Backing Image** (creation/backup) — replaced by CDI.
- ❌ **strict-local** data locality (we use `best-effort`, fine).
- ❌ Offline fast rebuilding, orphaned-instance management, engine **live**
  upgrade (V2 volumes must be detached to upgrade 1.12.x patches).

Known sizing note: the V2 instance manager busy-polls 2 pinned cores
(`data-engine-cpu-mask` default `0x3`). `guaranteedInstanceManagerCPU: "8"`
requests ~2.5 cores on the 32-core workers but only ~1.28 on the 16-core GPU
worker — an accepted under-request there; see the comment in `values.yaml`.

---

## Phase 1 — Verify Talos prerequisites (first boot)

The prereq patch is in `cluster-template.yaml` and applies on first boot of the
rebuilt cluster (for an existing cluster it needs `omnictl cluster template
sync` + a rolling reboot). Verify on each storage node:

```bash
# 2 GiB of hugepages (1024 x 2Mi)
talosctl -n <node-ip> read /proc/meminfo | grep -i hugepages_total   # expect 1024
# modules loaded
talosctl -n <node-ip> read /proc/modules | grep -E 'nvme_tcp|vfio_pci'
```

On the **GPU worker** also confirm the AI stack after Longhorn settles
(GPU must still be owned by nvidia.ko, not vfio):

```bash
kubectl -n llama-cpp get pods   # llama-cpp Running
kubectl -n comfyui  get pods    # comfyui Running
```

## Phase 2 — Verify the raw block device exists per storage node

The machine classes provision the V2 disk declaratively (`additional_disks`) —
nothing to do at rebuild time beyond verifying it attached. V2 needs a **raw
block device**: do **not** create a Talos `UserVolumeConfig`/`VolumeConfig` for
it and do not format it. Longhorn V2 claims the raw device directly, and Talos
leaves unreferenced disks untouched (the install disk is pinned to `/dev/sda`).

`/dev/sdb` is **not** stable across reboots — find the `by-id` path for
registration in Phase 3:

```bash
talosctl -n <node-ip> ls -l /dev/disk/by-id/
talosctl -n <node-ip> get disks        # Talos disk inventory
```

> For a NON-rebuild (existing VM): editing the machine class does not hot-add
> the disk. Hot-add once in Proxmox
> (`qm set <vmid> -scsi1 ssdpool:704,ssd=1,discard=on,iothread=1,cache=none,aio=io_uring`)
> and keep the machine-class entry so future reprovisions stay consistent.

## Phase 3 — Register the V2 block disk on each node (the one manual step)

The engine itself is already on at bootstrap (`v2DataEngine: "true"` syncs with
the chart; a fresh cluster has no attached volumes to block it). Verify:

```bash
kubectl -n longhorn-system get pods    # instance-manager (v2) pods present
kubectl get settings.longhorn.io v2-data-engine -n longhorn-system -o jsonpath='{.value}'  # "true"
kubectl get settings.longhorn.io v1-data-engine -n longhorn-system -o jsonpath='{.value}'  # "false"
```

Then register the disk on **each** storage node (Longhorn owns the `Node` CR;
add a `block`-type disk via UI or kubectl). UI: *Node → Edit Node and Disks →
Add Disk → Type: **Block**, Path: `/dev/disk/by-id/<id>`*. Verify:

```bash
kubectl -n longhorn-system get nodes.longhorn.io -o wide
# each storage node should show a schedulable block disk, V2 engine Ready
```

Remember: `createDefaultDiskLabeledNodes: "true"` means **no disks exist until
this step** — that is intentional (it keeps Longhorn off the OS partition).

## Phase 4 — Canary-validate V2 (especially the backup path) — THE GATE

Before trusting V2 for anything backed up, prove the **VolSync/Kopia** flow end
to end on a throwaway PVC (this repo's backup contract was built on V1):

1. Create a small PVC with `storageClassName: longhorn` (now the V2 class),
   write data, confirm it provisions and attaches on SPDK
   (`kubectl get volumes -n longhorn-system` — engine shows `v2`).
2. Add the pvc-plumber v4.0.1 backup labels (see `.claude/commands/add-backup.md`),
   then verify the in-namespace `volsync-kopia-repository` Secret + operator-owned
   `ReplicationSource`/`ReplicationDestination` appear and a backup completes:

   ```bash
   kubectl get secret,replicationsource,replicationdestination -n <canary-ns>
   ```
3. Confirm a CSI **VolumeSnapshot** is taken by the mover (the
   `driver.longhorn.io` VolumeSnapshotClass must work for V2) and that a restore
   into a fresh `longhorn` PVC succeeds. **If any step fails, stop deploying
   stateful apps and fix (or roll back, below) first** — there is no V1 fallback
   on this cluster.

## Phase 5 — Default class: nothing to do (verify only)

The default class is already correct from bootstrap — `longhorn`, routed to V2.
This phase used to be the V1→V2 cutover; on the V2-only rebuild it is verify-only:

```bash
kubectl get storageclass
# longhorn (default)  driver.longhorn.io  ... — exactly one default
kubectl get storageclass longhorn -o jsonpath='{.parameters.dataEngine}'   # "v2"
```

## Rollback (rebuilt cluster, worst case: V2 unusable)

The cluster is fresh, so rollback = re-point at V1 rather than migrate data:

1. In `values.yaml`: set `v1DataEngine: "true"`, `v2DataEngine: "false"`
   (detach any V2 volumes first — the setting is blocked otherwise), and
   `persistence.dataEngine: v1`.
2. V1 needs filesystem-backed disks: either temporarily allow the default disk
   (`createDefaultDiskLabeledNodes: "false"` — it lands on the OS disk, only
   acceptable as a stopgap) or wipe + reuse `/dev/sdb` as a mounted filesystem
   disk for V1.
3. File the V2 failure before re-attempting — the disk split and kernel prereqs
   stay valid either way.

## References

- Release notes: https://github.com/longhorn/longhorn/releases/tag/v1.12.0
- V1/V2 feature parity (1.12.0): https://longhorn.io/docs/1.12.0/v1-v2-volume-behavior-and-feature-parity/
- Talos support (hugepages + modules): https://longhorn.io/docs/1.12.0/advanced-resources/os-distro-specific/talos-linux-support/
- v2-data-engine setting (detach-to-change behavior): https://longhorn.io/docs/1.12.0/references/settings/
- Chart storageclass template (dataEngine gated on disableRevisionCounter):
  https://github.com/longhorn/longhorn/blob/v1.12.0/chart/templates/storageclass.yaml
