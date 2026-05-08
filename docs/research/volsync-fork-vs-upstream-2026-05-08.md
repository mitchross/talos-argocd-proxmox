# VolSync: stay on the perfectra1n fork or move to upstream backube?

Author: improv (research)
Date: 2026-05-08
Branch: refactor-replace-kyverno

This is a long-form answer to the operator's question after the cluster-wide
backup outage caused by pvc-plumber's `JobMutator` injecting an NFS volume into
mover Jobs that VolSync's reconciler then tried to "fix" via
`CreateOrUpdateDeleteOnImmutableErr` — deleting the running mover, looping.

The headline finding is at the very end. Read it first if you only have one
minute.

---

## 1. Why the perfectra1n fork exists

The fork's *whole reason for existing is the Kopia mover*. Upstream
[`backube/volsync`][upstream] does not ship a Kopia mover at all. Listing
`internal/controller/mover/` in each repo:

| Mover    | Upstream | Fork |
|----------|:--------:|:----:|
| rsync    |    yes   | yes  |
| rsync-tls|    yes   | yes  |
| restic   |    yes   | yes  |
| rclone   |    yes   | yes  |
| syncthing|    yes   | yes  |
| **kopia**|    **no**| **yes** |

The fork was created by `perfectra1n` on **2025-08-05** and PR #1
("Feat/implement kopia", merged 2025-08-13) added the entire Kopia mover.
Since then the merged-PR list is dominated by Kopia work: the maintenance CRD
(#14 / #15), the maintenance cronjob, hostname/multi-tenancy redesign,
identity overrides, custom CA, policy config, S2/zstd compression, parallelism
tuning, and the `moverVolumes` mechanism that replaced an earlier dedicated
`RepositoryPVC` field (PR #25, "remove RepositoryPVC in favor of moverVolumes",
merged 2025-12-31).

**Activity / health:**

- Fork last commit: `6966ac3` on **2026-03-22** (~7 weeks stale at time of
  writing). 16 stars, 5 forks, 5 open issues.
- Upstream last commit: **2026-05-07** (yesterday). 965 stars, 96 forks, 120
  open issues.
- Fork is **272 commits ahead, 93 behind** upstream/main, 121 files changed.
  The drift gap is *growing*: the most recent fork upstream merge was
  `348de681` on 2026-03-08; upstream has shipped v0.16.0-rc.3 since then.

**Roadmap for upstreaming:** none I could find. There is no open PR from
`perfectra1n` to `backube`, no design doc, no upstream issue advocating a
Kopia mover. The fork README explicitly directs users to the home-operations
Discord for support and treats itself as a long-running parallel project, not
a staging ground.

[upstream]: https://github.com/backube/volsync

## 2. Where `CreateOrUpdateDeleteOnImmutableErr` came from

**This is the most important finding in the report and the one that changes
the recommendation.** The function is **upstream code**, not fork code.

- Introduced in upstream PR [#302][pr302] by Tesshu Flower (Red Hat),
  commit `04487c79`, merged **2022-07-07** — i.e. four years ago, three years
  before the fork existed.
- Motivation: upstream issue [#291][issue291], "Upgrading VolSync when a job
  is running — job reconciles can fail repeatedly". When a VolSync upgrade
  changed the mover image (an immutable Job pod-template field), the
  controller would loop forever logging "field is immutable". The fix was
  intentional: detect that error class, **delete the Job, let the next
  reconcile recreate it with the new spec.**
- The fork's `internal/controller/utils/reconcile.go` is **byte-identical to
  upstream**. Both files share commit history (`970fc851`, `eecb75fd`).
- Both upstream restic mover (`internal/controller/mover/restic/mover.go:346`)
  and fork kopia mover (`internal/controller/mover/kopia/mover.go:547`) call
  it the same way: wrapping `CreateOrUpdate` on the mover Job.

**Behavior under admission-time spec mutation is identical between fork and
upstream.** Whenever VolSync's "desired" Job spec lacks a field that
admission injects, controller-runtime's diff-and-update produces an
immutable-field error on the next reconcile, and `CreateOrUpdateDeleteOnImmutableErr`
deletes the Job — including a still-running mover. There is no upstream
"tolerate drift" mode. There is no fork knob to turn this off. The behavior
is correct for its original purpose (image upgrades) and pathological for
admission-time volume injection.

> "Adds a util to do a CreateOrUpdate on a resource but also catch update
> errors about immutable fields and delete the resource (so it can be
> recreated on next reconcile). Uses the new util for mover jobs. This way
> if immutable fields (one common example may be the mover job image in the
> job pod) need update, the job can be deleted and recreated."  — PR #302

**Switching to upstream `backube/volsync` does not eliminate the problem
that broke the cluster.** Any admission-time mutation of mover Jobs will
race the controller's drift-correct loop on either flavor.

[pr302]: https://github.com/backube/volsync/pull/302
[issue291]: https://github.com/backube/volsync/issues/291

## 3. Kopia mover specifics

There is no upstream Kopia mover to compare. The closest analog is upstream's
`restic` mover (similar shape: external repo, retention policy, encryption,
shared bucket). Restic is fine, but the entire ecosystem switch from restic
to Kopia (deduplication, compression, performance) is well-documented and the
fork exists precisely because that switch isn't available upstream.

Fork-only Kopia features the operator currently uses or might want:

- `KopiaMaintenance` CRD (PR #15) — separate maintenance lifecycle.
- `spec.kopia.compression`, `spec.kopia.parallelism`, `spec.kopia.cacheCapacity`,
  `metadataCacheSizeLimitMB`, `contentCacheSizeLimitMB`.
- `spec.kopia.username` / `spec.kopia.hostname` overrides (multi-tenant
  identity inside one repo) — already exercised by the operator's
  `pvc-plumber` reconciler logic.
- `spec.kopia.policyConfig` — Kopia repository-wide policy embedded as Secret
  or inline JSON.
- `spec.kopia.additionalArgs` (free-form Kopia CLI flags).
- `spec.kopia.sourcePathOverride` — preserves logical path identity when
  backing up from a snapshot mount.
- Cross-namespace restore via `spec.kopia.sourceIdentity` on
  `ReplicationDestination` (per fork README), with auto-discovery in the
  same-namespace/same-name case.

Image: `ghcr.io/perfectra1n/volsync:vX.Y.Z`. Versioning is the fork's own
namespace and does not align with upstream tags (cluster runs `v0.17.11`;
upstream is on `v0.16.0-rc.3`).

## 4. S3 / object-store backends

**Both flavors fully support S3 for the movers they ship.** Restic (upstream)
and Kopia (fork) both consume S3 credentials via env vars on the mover Job —
no volume mounts, no admission injection.

Fork Kopia mover documents (`docs/usage/kopia/backends.rst`):

> Both `AWS_S3_ENDPOINT` and `KOPIA_S3_ENDPOINT` are supported. Region
> Configuration: `AWS_REGION`, `AWS_DEFAULT_REGION`, or `KOPIA_S3_REGION`.
> Credentials: standard AWS credential variables. Bucket: can be specified
> in the repository URL or via `KOPIA_S3_BUCKET`. TLS Control:
> `KOPIA_S3_DISABLE_TLS` for HTTP-only endpoints.

`KOPIA_S3_DISABLE_TLS=true` is exactly what the operator needs for in-cluster
RustFS over plaintext (the existing Barman setup uses the same pattern).

**S3 mode entirely sidesteps the admission-injection requirement.** The mover
Job needs no shared `/repository` mount; everything goes over the network.
The whole class of "controller fights admission webhook over Job spec" bugs
disappears.

**Performance for an in-cluster RustFS Kopia repo:**

- Kopia is content-addressed — chunks are uploaded to S3 by hash, snapshot
  manifests reference them. Listing snapshots is a metadata operation against
  a single index blob, not a directory walk. The `kopia snapshot list --all`
  pre-warm pvc-plumber does every 90s should perform comparably or better on
  S3 (Kopia caches blob index locally; subsequent calls hit the cache).
- Compression and dedup are unchanged — those happen client-side before
  upload.
- Latency floor on S3 is higher per-blob than NFS, but Kopia batches and the
  workload is throughput-dominated, not latency-dominated.
- RustFS already runs with Barman/CNPG in production — the operator has
  evidence it can handle similar throughput.
- One real downside vs NFS: reading snapshots for restore requires
  re-downloading content blobs (NFS read = local FS read). For a homelab
  this is a small concern; the cluster has 10G fabric and RustFS is
  in-cluster so latency is sub-ms.

## 5. Avoiding admission via in-spec volume declaration

The fork's `MoverConfig` (in `api/v1alpha1/common_types.go`) inlines
`MoverVolumes []MoverVolume`. `MoverVolumeSource` accepts three sources:

- `secret` (upstream + fork)
- `persistentVolumeClaim` (upstream + fork)
- **`nfs` (fork-only — added in commit `dd252aa3` on 2026-01-07,
  "allow NFS volumeMounts for moverVolumes")**

The implementation in `internal/controller/utils/utils.go`
(`UpdatePodTemplateSpecWithMoverVolumes`) appends each `moverVolume` to
`Spec.Template.Spec.Volumes` and adds a VolumeMount on `Containers[0]` at
`/mnt/<mountPath>`. Crucially this happens inside `configureJobSpec`, which
runs *inside the mutate-fn passed to `CreateOrUpdateDeleteOnImmutableErr`* —
so the NFS volume is part of the **desired** spec the controller compares
against. **No drift, no immutable-error, no Job deletion loop.**

Upstream has `MoverVolumes` too, but only with `secret` + `persistentVolumeClaim`.
**Upstream does NOT support NFS in `moverVolumes`.** This is a fork-only
capability and the only clean way to keep an NFS-backed Kopia repo without
admission-time mutation.

Two caveats if going this route:

1. The mount path is `/mnt/<mountPath>` not `/repository`. The kopia repo
   path lives in the operator's `KOPIA_REPOSITORY_PATH` env (deployment.yaml)
   and the kopia-maintenance CronJob's `--path=/repository`. Both would
   need to change, e.g. to `/mnt/repository`. Existing kopia repository
   metadata is path-independent (Kopia stores blob trees, not absolute paths)
   so the on-disk layout is unaffected.
2. `UpdatePodTemplateSpecWithMoverVolumes` only mounts on `Containers[0]`.
   VolSync mover Jobs are single-container — fine.

## 6. Migration paths

| Path | Mover image | Repo backend | JobMutator? | Drift loop risk |
|------|-------------|--------------|-------------|-----------------|
| **A. RustFS S3, fork** | `perfectra1n` | RustFS bucket | delete | gone |
| **B. RustFS S3, upstream** | `backube` (no Kopia) | n/a | n/a | **NOT VIABLE** — upstream has no Kopia mover |
| **C. NFS, upstream** | `backube` | NFS via `moverVolumes` | n/a | **NOT VIABLE** — upstream doesn't support NFS in `moverVolumes`, and no Kopia mover anyway |
| **D. NFS, fork, in-spec NFS via `moverVolumes`** | `perfectra1n` | NFS via `spec.kopia.moverVolumes` | delete | gone |

Paths B and C don't survive contact. The real choice is between **A
(NFS → S3, fork)** and **D (keep NFS, fork, replace JobMutator with
in-spec moverVolumes)**.

**Path A — switch to RustFS S3:**

- Add `volsync-kopia` bucket to RustFS (cluster already has admin creds via
  `rustfs-admin-credentials` ExternalSecret).
- Update `pvc-plumber` operator deployment to use S3 env vars
  (`KOPIA_REPOSITORY=s3://volsync-kopia`, `KOPIA_S3_ENDPOINT`,
  `KOPIA_S3_DISABLE_TLS=true`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`).
- Update `pvc_controller.go ensureExternalSecret` template to populate the
  same S3 vars on the per-PVC kopia-credentials Secret consumed by mover Jobs.
- Update `kopia-maintenance` CronJob to `repository connect s3` instead of
  `connect filesystem`.
- Delete `JobMutator` from pvc-plumber.
- Existing NFS-backed snapshots: either accept loss (homelab, drills passed
  on this branch) or one-shot `kopia repository sync-to s3` to mirror
  before cutting over.
- Rollback: re-enable `JobMutator` and revert env vars; NFS share untouched.
- Operational blast radius: medium. Touches operator code, mover credentials,
  maintenance CronJob, RustFS lifecycle.

**Path D — keep NFS, declare it in-spec:**

- Update `pvc_controller.go ensureReplicationSource` to add
  `moverVolumes: [{mountPath: "repository", volumeSource: {nfs: {...}}}]`
  to every generated RS. Same for ReplicationDestination.
- Backfill: existing RSes need the new field. Since they're operator-owned,
  bumping pvc-plumber and forcing a recreate (delete RS, label triggers
  reconcile) covers it.
- Update `KOPIA_REPOSITORY_PATH` env on operator and `--path` flag on
  maintenance CronJob: `/repository` → `/mnt/repository`.
- Delete `JobMutator` from pvc-plumber.
- Rollback: revert pvc-plumber image + delete recreated RSes; old
  `JobMutator` flow still works against the unmodified NFS share.
- Operational blast radius: small. No data migration. No new dependency.

## 7. Recommendation

**Go with Path A — switch to RustFS S3, stay on the fork. Delete the
JobMutator. Plan a RustFS-bucket-native VolSync layout from the start.**

Reasoning, no corporate-speak:

1. **The fork is the only viable Kopia option** — upstream has no Kopia
   mover and won't have one on any timeline you can plan against. Whatever
   you do, you stay on the fork. So "fork vs upstream" is a non-question;
   the real question is "fork on NFS or fork on S3".
2. **`CreateOrUpdateDeleteOnImmutableErr` is upstream architecture, not a
   fork bug.** Both Path A and Path D dodge it. But Path D dodges by
   carefully aligning what admission would have injected with what the
   controller's desired spec already contains — which means every future
   change to mover-spec construction in the fork (and there are many; see
   PRs #19, #25, #27 just in the last six months) is a chance for someone
   to subtly break that alignment. Path A makes it impossible to break:
   no shared volume, no admission, no drift.
3. **RustFS is already in production for CNPG Barman.** You know its
   failure modes, you have credentials, you have lifecycle automation, and
   you have monitoring. NFS is one more piece of infrastructure with its
   own failure modes (the share at `192.168.10.133`) for a workload that
   doesn't need filesystem semantics.
4. **Path D (the clever path) keeps NFS as a dependency** and keeps you
   shaped around a fork-only feature (`moverVolumes` + NFS) that, if
   abandoned, would force a migration anyway. Path A removes the
   coupling to NFS and uses only the standard S3 features Kopia and
   VolSync are guaranteed to keep supporting.
5. **The fork's own direction is toward in-cluster object storage.** PR #25
   ("remove RepositoryPVC in favor of moverVolumes") explicitly removed
   a purpose-built filesystem-repo affordance because the maintainer wants
   one less coupling between VolSync and the repo backend. S3 is the path
   of least friction for the fork's roadmap.

Path D is a respectable second choice if the operator wants to defer the
RustFS bucket work and ship a stable cluster *today*. It's strictly less
disruption: maybe 4 hours of operator code + manifest changes vs 1-2 days
for a full RustFS migration including a `kopia repository sync-to`. If
you're short on capacity, do D now and A on the next maintenance window.

## Surprising findings

- **The "fork drift-correct" framing in the operator's pre-research notes
  is wrong.** The drift-correct logic predates the fork by three years and
  comes from Red Hat. Cite PR #302 / issue #291 in the post-mortem; do not
  blame the fork maintainer.
- **Path C is impossible regardless of NFS or S3** because upstream has no
  Kopia mover. If anyone in the homelab community ever tells you "just
  switch to upstream backube/volsync", they don't know upstream is
  restic-only.
- **The fork's chart and image versions don't track each other** (this
  cluster runs chart 0.18.5 with image v0.17.11 — see
  `infrastructure/storage/volsync/values.yaml` comment). This is documented
  internally but is a gotcha for any future Renovate auto-bump policy.
- **Upstream is preparing a v0.16.0-rc.3 (released 2026-05-07).** The fork
  hasn't pulled an upstream merge since 2026-03-08. If a CVE lands in
  upstream before the next fork merge, the homelab is exposed. Worth
  watching `backube/volsync` releases manually until the fork catches up.

---

## Headline finding (read this paragraph if you read nothing else)

The drift-correcting "delete-on-immutable-err" loop that broke the cluster is
**upstream behavior** added by Red Hat in 2022 (PR #302 / issue #291),
inherited byte-for-byte by the fork. **Switching to upstream `backube/volsync`
does not fix it, and is impossible anyway because upstream has no Kopia mover
at all** — the fork's entire reason for existing is the Kopia mover. The
right fix is to make the controller's *desired* Job spec already contain
whatever was previously being injected at admission time. The cleanest way
to do that for the long term is to switch the Kopia repo from NFS to RustFS
S3 (which has no shared volume, period); the lower-risk short-term fix is
to declare the NFS share in `spec.kopia.moverVolumes` (a fork-only feature)
and drop the JobMutator. Either way: stay on the fork, delete the JobMutator,
and stop relying on admission-time mutation of mover Jobs.

## Sources

- [backube/volsync (upstream)](https://github.com/backube/volsync)
- [perfectra1n/volsync (fork)](https://github.com/perfectra1n/volsync)
- [Upstream PR #302 — delete/recreate jobs on immutable err](https://github.com/backube/volsync/pull/302)
- [Upstream issue #291 — job reconciles fail repeatedly](https://github.com/backube/volsync/issues/291)
- [Fork PR #25 — remove RepositoryPVC in favor of moverVolumes](https://github.com/perfectra1n/volsync/pull/25)
- [Fork commit dd252aa3 — allow NFS volumeMounts for moverVolumes](https://github.com/perfectra1n/volsync/commit/dd252aa3d0)
- [Kopia S3 backend docs](https://kopia.io/docs/reference/command-line/common/repository-create-s3/)
- [Kopia repository sync-to s3](https://kopia.io/docs/reference/command-line/common/repository-sync-to-s3/)
- Local files referenced:
  - `/home/vanillax/programming/talos-argocd-proxmox/infrastructure/storage/volsync/values.yaml`
  - `/home/vanillax/programming/talos-argocd-proxmox/infrastructure/controllers/pvc-plumber/webhooks.yaml`
  - `/home/vanillax/programming/pvc-plumber/internal/webhook/job_mutate.go`
  - `/home/vanillax/programming/pvc-plumber/internal/controller/pvc_controller.go`
