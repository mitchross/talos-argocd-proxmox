# September 2026 homelab repair rollout

**Purpose:** repair the immediate software failures found during the live lab
inspection and define what counts as a successful repair. **Status:** proposed
GitOps changes in one PR; this document is not evidence that production has been
repaired. Evidence was collected September 8–9, 2026 UTC. The owner must merge
the PR before Argo deploys it. Application auto-sync can begin immediately after
merge, including brief database and application interruptions under `Recreate`.

## The repair ticket

| Fault | Change in this PR | Acceptance after rollout |
|---|---|---|
| Temporal recovery CLI trapped under a 128 MiB cap | 768 MiB request, 1 GiB limit, bounded commands and 240-second Job deadline | Several scheduled runs finish; executable refaults, reads and disk queue fall |
| DCGM exporter trapped near its 512 MiB cap | 1 GiB request and 2 GiB limit | GPU metrics remain available; refault/stall rate and restarts settle |
| SurfSense Redis corrupt AOF; worker appears alive without working broker | Preserve the full AOF set, repair only the audited 10,659-byte tail; worker-specific readiness | Redis Ready, API/worker 2/2 Ready, document ingestion and search succeed |
| Flatnotes cannot open its Whoosh index | Preserve damaged index; rebuild from Markdown; startup/readiness checks | Existing notes open and searches return expected content |
| Perplexica snapshot cannot read root-owned configuration | Backup/restore mover uid 0, gid 568 using the documented root-owned-data exception | Next snapshot succeeds with nonzero files and includes configuration plus SQLite data |
| Keep returns misleading 401 after PostgreSQL connection loss | Validate pooled connections on checkout; bounded HTTP plus database readiness | Backend recovers and normal Alertmanager deliveries succeed |
| Seven PostgreSQL instances invisible to Prometheus | Six exporters; repair PostHog metrics Service labels; CI checks the complete discovery path | All ten instances have `up=1`, `pg_up=1`, no scrape errors |
| PostHog Kafka/ClickHouse monitors select no Services | Match Service labels to existing ServiceMonitors | Both existing metrics targets appear and scrape successfully |
| Vulnerable Immich/PostHog PostgreSQL servers | Same-major security patches, pinned by digest; retain Immich vector extension versions | Servers report 17.11 / 15.19; queries, vector search and application operations succeed |
| Failures obscured by green schedules/Running pods | Alerts for last-backup failure, missing PG targets, webhook delivery errors, reclaim storms and stalled recovery Jobs | Faults are visible without relying solely on the broken receiver |

The VPA controllers were functioning. These fixes address container limits,
missing discovery and application faults that VPA does not automatically repair.
New fixed-size exporters are excluded from VPA and have no readiness probe that
could remove a healthy database from its Service.

## Before merging

Use the intended authenticated cluster context, `kubectl`, Argo read access and
Prometheus/Grafana access. Confirm other maintenance has finished; the Elite node
was cordoned during this inspection and must not be uncordoned by this repair.
Check current failures against the incident before authorizing deployment:

```sh
kubectl config current-context
kubectl get nodes
kubectl -n argocd get applications
kubectl -n temporal-worker-controller get cronjobs,jobs,pods
kubectl -n immich get snapshots.kopiur.home-operations.com
kubectl -n posthog get snapshots.kopiur.home-operations.com
kubectl -n perplexica get snapshots.kopiur.home-operations.com
```

Confirm successful, recent Immich/PostHog PostgreSQL snapshots and accessible
repository credentials before database restart. A successful snapshot is not a
proven restore. Preserve evidence of the existing incidents. If backups are
unavailable, data ownership has changed, or a different Redis/index failure has
appeared, stop and investigate; do not loosen the recovery guards to force sync.

The Redis repair intentionally discards a bounded corrupt tail after retaining
all original bytes. It cannot promise zero lost or replayed queued tasks. Review
[SurfSense recovery](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/ai/surfsense/RECOVERY.md) and
[Flatnotes recovery](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/home/project-nomad/flatnotes/RECOVERY.md) before
merge. Their init containers operate while the old writer is stopped and leave
unexpected conditions for inspection rather than trying broad repairs.

The PostgreSQL patches are same-major restarts, not dump/restore migrations.
PostHog's upstream Compose still pins 15.12; this is a narrow security exception
to following that pin, retaining the Alpine family and application versions.
See [its upgrade checklist](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/development/posthog/UPGRADE.md).
Immich has no compatible upstream image containing the fixed server: the new
server stages only the unchanged vector extension files from the old pinned
image. Review [the Immich procedure](https://github.com/mitchross/talos-argocd-proxmox/blob/main/my-apps/media/immich/postgres/UPGRADE.md).
The donor does not run PostgreSQL or mount the data PVC.

## After Argo reconciles

1. **Check actual revisions and resources.** Every affected Application must
   report the merged revision with a successful sync; `Healthy` alone is not
   sufficient. Inspect init logs if recovery stops. Never delete a retained
   recovery archive merely to get a green rollout.
2. **Retire the old Temporal Job only after verifying its replacement template.**
   Follow the [Temporal rollout ordering](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/controllers/temporal-worker-controller/README.md#rollout-and-verification),
   including owner/UID checks. The existing immutable Job keeps the old limit and
   blocks subsequent schedules under `Forbid`. The PR itself does not delete it.
3. **Verify the repaired services.** Use the app-specific acceptance checks above,
   inspect restart deltas, and check PostgreSQL server/extension versions. For
   Keep, use the [readiness and delivery checks](https://github.com/mitchross/talos-argocd-proxmox/blob/main/monitoring/keep/README.md#database-restart-and-misleading-http-401).
   A synthetic alert would send a real message and requires an explicitly
   authorized test; ordinary delivery observations remain read-only.
4. **Verify metrics and backup outcomes.** In Prometheus, inspect `pg_up` grouped
   by namespace: gitea, hindsight, immich, intercept, keep, langfuse,
   paperless-ngx, posthog, surfsense and temporal must all be present and equal to
   1. Check exporter `up` and `pg_exporter_last_scrape_error` too. Wait for a fresh
   Perplexica snapshot; a Ready schedule or a zero consecutive-failure counter
   did not prove backup success during this incident.
5. **Measure the disks again.** Observe several Temporal cycles and at least
   30 minutes of ordinary load after both thrashing processes settle. Compare
   disk reads, queue depth, await, file-cache refaults and memory pressure against
   the incident. Repeat only bounded scratch-file tests with confirmed free
   space. Do not use raw-device write tests on live storage or infer hardware
   failure from the incident's abnormal queue depth.
6. **Prove recovery separately.** Restore a fresh Perplexica and PostgreSQL
   snapshot into isolated destinations, validate contents and application
   consistency, and remove only those test resources afterward. This is an
   acceptance follow-up, not a claim established by the local fixture tests.
   Do not repoint production PVCs or overwrite current databases to test backups.

## Failure and rollback

A Git revert through another PR restores configuration; it does not undo a data
repair. Keep original AOF/index archives until application results have been
verified. Recovery runbooks require stopping writers before restoring those
artifacts; the old corrupted originals reproduce the pre-repair failure.

If database startup fails, retain the PVC and inspect logs and extension mounts.
Do not delete the PVC, rerun initialization over it, or change PostgreSQL major
versions. The Immich procedure documents the compatible previous image and the
security consequence of rollback. For Temporal/DCGM, preserve the increased
memory budgets while diagnosing; reinstating the old caps recreates the fault.
Keep's pre-ping cannot rescue every request interrupted mid-transaction, and its
upstream HTTP error classification remains imperfect.

## Work that still needs a separate maintenance plan

This PR does not make three Coroot replicas independent: every Keeper PVC's sole
Longhorn copy was on SFF, and the pinned operator omits readiness gating during
rollout. A coordinated storage-copy and quorum-aware placement plan is required;
a compute-only shuffle would leave the physical failure dependency intact.
Likewise, increasing Longhorn replicas globally is not part of this repair.

Control-plane SSD replacement, the worn Elite data SSD, NAS cooling, NAS
`sync=disabled` durability, storage placement and restore drills remain on the
hardware/recovery plan. Disk purchasing and movement should follow the clean
post-repair measurements. The inspection identified useful hardware; the first
repair is stopping software from abusing it.

## Validation recorded before deployment

The repair scripts have regression coverage for failure, interruption and
preservation guards. Real Redis/Flatnotes images exercised synthetic corrupt
fixtures without production data. A read-only uid 0:568 container with every
capability dropped read root-owned 0600 and group-readable 0664 fixture files,
and correctly failed on unrelated non-root 0600 data and attempted writes.

A synthetic PostHog database created with 15.12 reopened on 15.19 with all 1,000
canary rows and the identical content checksum; `pg_stat_statements` remained
functional. The actual exporter image scraped PostgreSQL using local split
credentials, uid 65534 and a read-only root filesystem. Immich's test reopened
an old-image database with all eight live extension types and a real vector
index; indexed results matched, new writes and reindex worked, and fresh
initialization also passed. These are compatibility tests, not restored copies
of the production databases.

Sources: [PostgreSQL security advisory](https://www.postgresql.org/support/security/CVE-2026-14669/),
[PostHog upstream Compose](https://github.com/PostHog/posthog/blob/master/docker-compose.base.yml),
and the app-owned runbooks linked above. Manifests and test commands in this PR
are the deployable source of truth.
