# Storage tiers — which StorageClass for which PVC

**The one rule:** *does this volume fsync on every write?*
Databases do (every commit). Almost nothing else does.

That single question decides the tier, because the tiers are not "fast" and "slow" — they each
win at a different thing, and picking wrong makes things **worse**, not just suboptimal.

## The measurements this rule is built on

Each measured through its **full stack** (fio, 2026-07-13):

| | 4K fsync write | 4K random read | 1M seq read | 1M seq write |
|---|---|---|---|---|
| **`longhorn`** (consumer EDILOCA NVMe, in Proxmox) | **259 IOPS** | **161k IOPS** | **2310 MB/s** | 109 MB/s |
| **`truenas-flash`** (enterprise SATA SSD, RAIDZ1, over NVMe-oF) | **~3,000 IOPS** | 68k IOPS | 1018 MB/s | **~750 MB/s** |

Read that table twice. **Longhorn's consumer NVMe out-reads the enterprise SATA by 2x.** NVMe beats
SATA at reading, and power-loss protection does not change that. What the consumer drive *cannot*
do is write: 259 fsync IOPS is a DRAM-less, no-PLP write cliff.

So: **`truenas-flash` is ~11x on writes and ~2x WORSE on reads.** It is a *write* tier, not a
"fast" tier. Moving a read-heavy volume onto it is a **downgrade**.

## The decision tree

```
                    Does more than one pod mount it,
                    or is it bulk media / model weights?
                              |
                 yes ---------+--------- no
                  |                       |
          SMB / NFS classes        Is it a DATABASE?
       (BigTank or ai-pool)        (fsyncs every write)
                                          |
                            yes ----------+---------- no
                             |                         |
                     truenas-flash                 longhorn
                     (NVMe-oF, RWO)             (the default)
```

### 1. `truenas-flash` — databases only

Postgres, MySQL, ClickHouse, Kafka/Redpanda, Redis (persistent), Prometheus TSDB, Loki,
Qdrant, Meilisearch. Anything whose write path is "append to a log, fsync, acknowledge."

**RWO only.** NVMe-oF is block storage — it cannot be RWX. A block device mounted by two
writers is a corrupted block device.

### 2. `longhorn` — the default, and it stays the default

App config, app state, caches, libraries, anything read-mostly, and **anything needing RWX**
(Longhorn provides that via a share-manager pod). It reads better than the flash tier and it is
node-local (no NAS dependency). **When in doubt, use Longhorn.**

### 3. SMB / NFS — bulk and shared

Media libraries, model weights, anything multiple pods read, anything you want to browse by hand.
Files, not blocks. See `infrastructure/storage/CLAUDE.md` for the class list.

## Why not "just put everything on flash"

Three independent reasons, each sufficient on its own:

1. **Reads get worse.** See the table. Most PVCs are read-mostly.
2. **It adds a NAS dependency.** A Longhorn volume survives the NAS being down; a `truenas-flash`
   volume does not mount. The cluster still *boots* (volumes attach at pod-schedule time, not VM
   boot), but those pods will not start. Don't spend that dependency on a volume that gains nothing.
3. **Backups break silently unless you also swap the kopiur component.** See below. This is the
   one that will actually hurt you.

## ⚠️ The backup trap — read this before moving any PVC

A `VolumeSnapshotClass` is bound to exactly **one** CSI driver.
`my-apps/common/kopiur-backup` injects `volumeSnapshotClassName: longhorn-snapclass`, which is
bound to `driver.longhorn.io`. It **physically cannot snapshot a `csi.truenas.io` volume.**

Move a backed-up PVC to `truenas-flash` without changing anything else and it will look perfectly
backed up in git while producing **nothing**. You find out during a restore.

The fix — stack the flash override **after** the base component:

```yaml
components:
  - ../../common/kopiur-backup        # base
  - ../../common/kopiur-backup-flash  # swaps in truenas-snapshot
```

Then **verify, do not assume**:
```bash
kubectl -n <ns> get snapshot     # must reach Succeeded with a NON-ZERO file count
```

CNPG databases are the exception: they back up via **Barman to S3**, which does not use a
VolumeSnapshotClass at all. A CNPG PVC can change storage class without touching its backups.
(Never add kopiur CRs to a CNPG PVC — that rule is unchanged.)

## Migration risk ladder

Move in this order. Each rung is safe only because the one before it proved something.

**Rung 1 — backup-exempt databases (zero backup risk, they have no backups by design).**
Also serves as the canary for the whole NVMe-oF path.
`posthog` (clickhouse, postgres, redis7, redpanda), `prometheus-stack` (TSDB),
`redis-instance`, `searxng` (redis).

**Rung 2 — CNPG (Barman-backed; no VolumeSnapshotClass dependency).**
`immich-database`, `paperless-database`, `temporal-database` (+ their WAL volumes).
Note: CNPG cannot change `storageClass` in place — it needs a new cluster + switchover, or a
restore from Barman. Plan it as a database operation, not a YAML edit.

**Rung 3 — kopiur-backed databases. ONLY after a `kopiur-backup-flash` Snapshot has been
observed reaching `Succeeded` with non-zero files.**
`gitea/gitea-postgres-data`, `project-nomad/mysql-data`, `project-nomad/qdrant-data`,
`karakeep/meilisearch-pvc`, `kafka/data-0-dev-kafka-dual-role-0`, `loki-stack/*`.

## Everything else stays on Longhorn

Every other PVC — `immich/library`, `home-assistant/config`, `jellyfin/config`, `n8n/data`,
`open-webui/storage`, `perplexica`, `paperless-ngx/data`+`media`, `karakeep/data-pvc`,
`frigate/frigate-config`, `copyparty`, `fizzy`, `presenton`, `flatnotes`, `tubesync/config-pvc`,
`gitea-shared-storage`, `homepage-dashboard`, `zomboid-data`, `restore-canary`, `registry`, and
all the caches (`immich-ml-cache`, `act-runner-docker-cache`, `swarmui/*`, `nomad-storage`,
`protomaps-data`, `openmeteo-data`, `embeddings-model-cache`) — is app state or read-mostly.
**It gains nothing from flash and would read slower there.** Leave it.
