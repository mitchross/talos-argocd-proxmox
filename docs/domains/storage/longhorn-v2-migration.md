# Longhorn 1.12.0 — V2 (SPDK) Data Engine Rebuild Runbook

> ## ⚠️ OUTCOME (2026-06-12): V2 RETIRED — cluster returned to V1
>
> The V2 rebuild below was executed 2026-06-11/12 and **failed in production
> within hours**, during the post-nuke mass restore. The failure matched open
> Longhorn 1.12 V2 bugs (both targeting 1.13.0):
>
> - [#13315](https://github.com/longhorn/longhorn/issues/13315) — interrupted
>   rebuild permanently poisons replica metadata ("active chain parent … does
>   not match head parent")
> - [#13314](https://github.com/longhorn/longhorn/issues/13314) — volume can
>   crash again after automatic reattachment
>
> Sequence: 25 parallel VolSync restores → SPDK instance-manager crash →
> replica-rebuild wave → NVMe-TCP keep-alive timeouts → self-sustaining fault
> loop → 10 freshly-restored volumes left with corrupted single-copy replica
> chains → full Proxmox host reboot required to clear poisoned kernel NVMe
> state. Forensics: README.md "V2 data-engine attach storm" playbook.
> Hardware (consumer-SSD stripe, CPU oversubscription) amplified the load,
> but the defects are upstream software.
>
> **The reversal (in Git 2026-06-12):** single 800G disk restored in the
> machine classes, V2 patches removed from the cluster template, Helm values
> back to the V1 engine (chart default). Migration is nuke +
> restore-from-backup — engines cannot be flipped in place. **Do not
> re-attempt V2** without (1) a Longhorn release with both bugs fixed,
> (2) a passed restore-canary DR drill, and (3) ideally per-worker physical
> disks. The rest of this document is the historical record of the V2 design.

> **Status (historical):** the rebuild target config was fully in GitOps. The
> cluster was **V2-only**: `v2DataEngine: "true"`, `v1DataEngine: "false"`, and
> the default `longhorn` StorageClass routed to the V2 engine via
> `persistence.dataEngine: v2`. All of it applied when the **rebuilt** cluster
> bootstrapped.
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

Registration of the raw `/dev/sdb` device is **fully declarative** (GitOps,
no manual step). The earlier "manual on purpose" rationale was wrong: QEMU
derives the disk serial from the drive name, so the `additional_disks` device
(`scsi1`) has the **same stable by-id on every provider-built VM** —
`/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1` (verified live
2026-06-11 across all rebuilt workers). The cluster template's
`longhorn-v2-default-disk` patch (workers + gpu-workers) stamps:

- label `node.longhorn.io/create-default-disk: "config"`
- annotation `node.longhorn.io/default-disks-config:
  '[{"name":"v2-block-0","path":"/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1","allowScheduling":true,"diskType":"block","storageReserved":0}]'`

and longhorn-manager (with `createDefaultDiskLabeledNodes: "true"`) registers
the block disk itself when the node has no disks yet. Talos applies
nodeLabels/nodeAnnotations hot — no reboot.

Source-verified against longhorn-manager v1.12.0 (2026-06-11):

- `types.CreateDisksFromAnnotation` explicitly supports `"diskType":"block"`
  (the docs page omits it — code is authoritative).
- `KubernetesNodeController.syncDefaultDisks` applies the config "even if the
  node has been labeled after initial registration", as long as the Node CR
  has **zero disks** — so a late template sync still registers the disks. If
  a node somehow doesn't pick it up, delete its `nodes.longhorn.io` CR
  (longhorn-manager recreates it and applies the config) — never on a node
  that already holds replicas.
- `storageReserved: 0` in the annotation means "recompute from the
  `storage-reserved-percentage-for-default-disk` setting" (default 30 — would
  reserve ~211G of each 704G disk). values.yaml pins
  `storageReservedPercentageForDefaultDisk: "0"` because every disk here is a
  dedicated raw device.

Paste-able alternative (no UI). For each storage node IP, discover the stable
`by-id` of the V2 disk, then patch the Longhorn `Node` CR:

```bash
NODE_IP=192.168.10.x        # Talos node IP
K8S_NODE=talos-...-workers-xxxxx   # its kubernetes node name (kubectl get nodes)

# 1. Find the V2 disk: the ~704G (worker) / ~672G (GPU) device that is NOT the
#    system disk. Confirm size + which /dev/sdX it is:
talosctl -n "$NODE_IP" get disks
# 2. Resolve that /dev/sdX (e.g. sdb) to its stable by-id symlink:
talosctl -n "$NODE_IP" ls -l /dev/disk/by-id/ | grep -w sdb   # -> note the by-id name
BYID=/dev/disk/by-id/<paste-the-by-id-here>

# 3. Register it as a schedulable BLOCK disk (diskType: block = V2/SPDK):
kubectl -n longhorn-system patch nodes.longhorn.io "$K8S_NODE" --type merge -p "{
  \"spec\": { \"disks\": { \"v2-block-0\": {
    \"path\": \"$BYID\", \"diskType\": \"block\",
    \"allowScheduling\": true, \"storageReserved\": 0, \"tags\": []
  } } } }"
```

Verify (all storage nodes show a schedulable block disk, V2 Ready):

```bash
kubectl -n longhorn-system get nodes.longhorn.io -o wide
kubectl -n longhorn-system get nodes.longhorn.io "$K8S_NODE" \
  -o jsonpath='{.status.diskStatus.v2-block-0.conditions}'   # Schedulable=True
```

Remember: `createDefaultDiskLabeledNodes: "true"` means **no disks exist until
this step** — that is intentional (it keeps Longhorn off the OS partition), so
until you finish all nodes, `longhorn`-class PVCs stay `Pending` (no data loss).

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
