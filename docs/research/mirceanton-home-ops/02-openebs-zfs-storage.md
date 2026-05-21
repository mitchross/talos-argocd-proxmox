# mirceanton/home-ops — OpenEBS / ZFS Storage Layer

Author: research (study mode)
Date: 2026-05-18
Source: `mirceanton/home-ops` @ main + "From 3 to 1: Why I 'Downgraded' My Homelab"

> External reference. Not this repo's design. No comparison drawn here.
> This is the storage substrate the backup system (doc 01) sits on.

---

## 1. Why this layer exists (the rationale, from the video)

He ran a 3-node Talos cluster with **Rook-Ceph** distributed NVMe storage
over dual-10GbE. He tore it down to **a single node** because:

- HA was a "lie": redundant compute in front of a **single NAS** and
  **single network path** — most real workloads (media stack, bulk apps)
  mounted NAS storage, so node redundancy protected nothing that mattered.
- Ceph cost: heavy CPU/RAM/network just to keep itself alive, and it was
  the *only* reason the 10G fabric was a hard requirement.
- Power (~250 W idle, ~100 W wasted ≈ €250–300/yr), noise, heat,
  complexity, maintenance surface.

Conclusion he states: HA at home is an **economic/operational** decision,
not a technical one. He optimised for **durability, not availability**.

So the storage layer was redesigned around: no distributed storage, no
consensus, no replication traffic — local ZFS with disk-level redundancy
for important data, disposable storage for caches, and VolSync→S3 for
durability.

---

## 2. What replaced Ceph: OpenEBS ZFS-LocalPV

`apps/storage-system/openebs/app/helm-release.yaml` (chart via
OCIRepository). Only the local ZFS engine is enabled; everything else is
explicitly off:

```yaml
engines:
  local:
    zfs:     {enabled: true}
    lvm:     {enabled: false}
    rawfile: {enabled: false}
  replicated:
    mayastor: {enabled: false}     # no distributed storage
analytics: {enabled: false}
alloy:     {enabled: false}
loki:      {enabled: false}
openebs-crds:
  csi: {volumeSnapshots: {enabled: false}}   # snapshot CRDs come from snapshot-controller
```

- `zfs-localpv` provisioner, single replica controller + node plugin
  (single-node cluster), tight CPU/mem requests+limits.
- `localpv-provisioner` also enabled with a non-default
  `openebs-hostpath` class (for data that doesn't need ZFS).
- **Talos-specific tweaks:**
  - `zfs.bin: /usr/local/sbin/zfs` — Talos installs ZFS at a non-standard
    path.
  - `zfsNode.encrKeysDir: /var/local/openebs/keys` — `/home` is read-only
    on Talos; encryption keys must live under a writable `/var` path.

### 2.1 Talos enablement

`talos/patches/zfs.yaml`:

```yaml
machine:
  kernel:
    modules:
      - name: zfs
```

Just loads the ZFS kernel module. **The ZFS pools themselves are NOT in
Git** — `data-pool` and `cache-pool` (see §3) are created out-of-band on
the host. This is an important gap to remember: Git declares *consumption*
of the pools, not their creation.

### 2.2 Ordering

`apps/storage-system/openebs/app.ks.yaml` → `dependsOn: snapshot-controller`.
The snapshot-controller (`apps/storage-system/snapshot-controller/`) owns
the VolumeSnapshot CRDs (OpenEBS chart's own snapshot CRDs are disabled to
avoid a conflict). VolSync's `copyMethod: Snapshot` depends on this chain
being up.

---

## 3. The two-pool, two-class model

`apps/storage-system/openebs/app/storage-class.yaml` defines two
StorageClasses, mapping to two ZFS pools — this is the video's
"mirror for important data, disposable pool for cache" expressed in YAML:

| StorageClass | Pool | Default? | recordsize | Purpose |
|---|---|---|---|---|
| `openebs-zfs` | `data-pool` | **cluster default** (`is-default-class: true`) | `16k` | Important PVCs. Video: a **ZFS mirror** local to the node → survives a disk failure. 16k recordsize suits DB/general mixed I/O. |
| `openebs-zfs-cache` | `cache-pool` | no | `128k` | Cache/scratch volumes. Video: a **single-disk** pool — can be lost and recreated. 128k recordsize suits large sequential/throughput data. |

Shared parameters: `provisioner: zfs.csi.openebs.io`,
`compression: zstd`, `dedup: off`, `fstype: zfs`, `shared: yes`,
`allowVolumeExpansion: true`.

> Open question (tracked): the VolSync component default is
> `VOLSYNC_CACHE_SNAPSHOTCLASS:=openebs-zfs` — i.e. the Restic mover cache
> PVC defaults to the **data** pool, not `openebs-zfs-cache`. Whether
> that's intentional (cache pool reserved for app caches only) or an
> oversight is unresolved.

### 3.1 Snapshot class

`apps/storage-system/openebs/app/snapshot-class.yaml`:

```yaml
kind: VolumeSnapshotClass
metadata:
  name: openebs-snapshots
  annotations: {snapshot.storage.kubernetes.io/is-default-class: "true"}
driver: zfs.csi.openebs.io
deletionPolicy: Delete
```

This is the class VolSync's `copyMethod: Snapshot` uses (component default
`VOLSYNC_SNAPSHOTCLASS:=openebs-snapshots`). ZFS-native snapshots are what
make the "app keeps running while we back up a frozen copy" property work,
and they're cheap because they're copy-on-write at the ZFS layer.

---

## 4. Pool health: scrub

`apps/storage-system/openebs/app/zfs-scrub.cronjob.yaml`:

- CronJob `data-pool-zfs-scrubber`, `0 3 * * 0` (Sun 03:00),
  `concurrencyPolicy: Forbid`, `backoffLimit: 0`.
- Pinned to node `home-ops` (the single node).
- Image `ghcr.io/heavybullets8/zfs-scrubber`, `privileged: true`,
  hostPath-mounts `/dev/zfs`, env `ACTION=scrub ZFS_POOL=data-pool`.
- Only `data-pool` is scrubbed — consistent with `cache-pool` being
  disposable (no integrity guarantee needed there).

`apps/storage-system/zfs-exporter/` adds ZFS metrics + a Grafana
dashboard + Prometheus rules (observability, not data path).

---

## 5. How storage and backup connect: the Ceph→OpenEBS migration

The video's migration *is* the backup system's restore path (doc 01 §6):

1. Backed up all "safe" PVCs to the Garage **S3 instance on the NAS** via
   VolSync ReplicationSources.
2. Redeployed the whole cluster on **OpenEBS ZFS** (Ceph fully removed).
3. New PVCs created with the component's `dataSourceRef → ${APP}-dst`;
   VolSync mover Jobs **pulled the data back from S3** into the new ZFS
   volumes automatically.

So the namespace-agnostic Restic repo path (doc 01 §3.1) doubled as a
**whole-storage-backend migration tool**. The backup system isn't just DR
— it's the data-mobility layer that made the single-node downgrade
low-risk.

---

## 6. The durability story around it (3-2-1)

Storage durability is layered *on top* of this local-ZFS base:

- **NAS-resident data** (media/bulk): ZFS snapshots → offsite NAS
  replication → Backblaze B2 = full 3-2-1.
- **Cluster-local app data**: VolSync → Garage S3 on NAS → then inherits
  the same 3-2-1 pipeline.
- **Config/state**: Talos YAML + Flux Git repo → rebuild a node "in
  minutes".

Local ZFS provides *disk-failure* protection (mirror) and cheap
snapshots; everything beyond a single-disk loss is handled by
VolSync→S3→3-2-1, not by the storage layer itself. Accepted tradeoff:
**availability during reboots/maintenance** ("everything takes a short
nap"), explicitly deemed acceptable for a homelab.

---

## 7. Layer map (textual)

```
Talos node "home-ops"
 ├─ kernel module: zfs            (talos/patches/zfs.yaml)
 ├─ ZFS pools (created off-Git):
 │    ├─ data-pool   = mirror     → important data, scrubbed weekly
 │    └─ cache-pool  = single disk → disposable
 ├─ OpenEBS zfs-localpv (zfs.csi.openebs.io)
 │    ├─ SC openebs-zfs        → data-pool   (default, 16k)
 │    ├─ SC openebs-zfs-cache  → cache-pool  (128k)
 │    ├─ SC openebs-hostpath   → localpv hostpath
 │    └─ VSC openebs-snapshots (default)
 ├─ snapshot-controller (owns VolumeSnapshot CRDs)
 └─ VolSync (consumes SC openebs-zfs + VSC openebs-snapshots)
        └─ Restic → Garage S3 (NAS) → 3-2-1 (offsite NAS + Backblaze B2)
```
