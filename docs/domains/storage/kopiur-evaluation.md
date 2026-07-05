# kopiur evaluation — engine candidate for the backup path

> **Outcome (2026-06-27): adopted.** kopiur replaced the retired pvc-plumber +
> VolSync stack. The "thin DRY layer" recommended here shipped as the
> [`my-apps/common/kopiur-backup` Kustomize component](kopiur-backup-architecture.md#2-how-a-kustomize-component-composes-read-this-if-components-are-new).
> Current architecture: [`kopiur-backup-architecture.md`](kopiur-backup-architecture.md).

This is the 2026-06 evaluation of **kopiur** (home-operations' Kopia-native Rust
backup operator). It is retained for the verified facts and config shapes below.

## Why kopiur

- It implements **restore-before-bind** via the Kubernetes Volume Populator
  contract: a PVC with `dataSourceRef` stays `Pending` until its `Restore`
  populator hydrates it, so an app never boots on an empty volume.
  `onMissingSnapshot: Continue` = restore-if-exists-else-fresh; `Fail` = hard stop.
- kopiur is intentionally **explicit** by design (own your PVC, wire
  `Restore` + `dataSourceRef` yourself) — it does not ship a label-driven
  auto-wiring or coverage-audit layer, so that convenience/safety layer is ours
  (the `kopiur-backup` Kustomize component).
- Node-local mover (data gravity): a per-PVC mover Job co-locates on the PVC's
  node, streaming bytes via kopia; the controller never pulls data centrally.
- Webhooks target **only `kopiur.home-operations.com` CRDs**, never PVCs/Pods —
  an app deploy is never blocked by a kopiur outage.

Only VolSync and kopiur implement the populator-hold. Velero, K8up, Stash, and
Gemini back up fine but restore as a separate imperative step, which reintroduces
the blank-PVC-then-corrupt race this system exists to prevent.

### Why the hold matters (restore-after-the-fact is too late)

1. **The good snapshot can be gone** — the blank instance's own scheduled backup
   snapshots the empty state; retention ages out the real one.
2. **Irreversible external side effects** — re-onboarding rotates API keys/tokens;
   restoring the old DB brings back revoked creds (e.g. Sonarr, HA OAuth).
3. **Divergent writes** — the app wrote real data to the blank volume; restoring
   the old DB loses it and desyncs from disk.
4. **Lockout deadlock** — auth-bearing apps (Vaultwarden, an IdP) lose the
   credential that lived in the data.

Sharpest example: a game-server world save (Minecraft/Valheim/Zomboid) —
irreplaceable, no login, and the fresh-world backup overwrites the real one.

## Verified kopiur facts (as of `0.5.1`)

- **OCI chart** at `oci://ghcr.io/home-operations/charts/kopiur`, rendered locally
  via Kustomize `helmCharts:` (`infrastructure/controllers/kopiur-operator/`).
  Chart version == app version (e.g. `0.5.1`), tags carry no `v` prefix. Manifests
  come from our own git source, so no AppProject `sourceRepos` exception is needed.
- **CRDs (`v1alpha1`):** `Repository`, `ClusterRepository`, `SnapshotPolicy`,
  `Snapshot`, `SnapshotSchedule`, `Restore`, `Maintenance`, `RepositoryReplication`.
- **S3 backend:** `backend.s3.{bucket, prefix, endpoint, region}`; `endpoint` is a
  bare `host:port` (no scheme/slash); TLS-off is `tls.disableTls: true`.
  `ClusterRepository` secret refs must carry an explicit `namespace` (webhook-enforced).
- **Creds Secret keys:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `KOPIA_PASSWORD`.
- **Chart values:** `installScope` (`namespaced`|`cluster`), `installCRDs: true`,
  `webhook.failurePolicy: Fail`, `webhook.tls.mode: self` (self-signs at runtime —
  no cert-manager hook Job, ArgoCD-safe), per-image `image.{controller,webhook,mover}.tag/digest`.
- **Mover:** statically-linked Rust binary + official kopia, distroless ~70 MB;
  reads a downward-API JSON work spec, streams `kopia --json`, PATCHes progress to
  `status`. Co-locates on the PVC's node for RWO (avoids Multi-Attach).
- **Backend-down safety:** kopiur uses a repository health-probe / preflight
  (there is no `wait-for-rustfs` MAP anymore). A snapshot against an unreachable
  repo errors and retries; a restore against an unreachable repo leaves the PVC
  `Pending` rather than binding empty.

## Config shapes that matter (corrected against real deployments)

Cross-checked against onedr0p/home-ops (chart `0.2.0`, its reusable `components/kopiur`)
and eleboucher/homelab:

| Field | Why it matters |
|---|---|
| `copyMethod: Snapshot` + `volumeSnapshotClassName: longhorn-snapclass` | CSI snapshots won't fire on Longhorn without them |
| **ClusterExternalSecret fanout** of `kopiur-rustfs` | the mover in the app namespace can't reach the ClusterRepository creds (in `kopiur-system`) otherwise. Delivered to every namespace labeled `kopiur.home-operations.com/repo: cluster-kopia`; secret name must match the repo's `secretRef.name`. Least-privilege alternative to `features.credentialProjection` (which needs cluster-wide secret create/patch RBAC) |
| `mover.securityContext {runAsUser/runAsGroup}` + `mover.podSecurityContext.fsGroup` | restored files get correct ownership. **`fsGroup` is pod-level — under `mover.podSecurityContext`, NOT `mover.securityContext`** (the container SC rejects `fsGroup` under strict CRD validation) |
| Restore `source.fromPolicy` (vs `identity`) | simpler; what both reference repos use |
| Schedule `concurrencyPolicy: Forbid` | no overlapping snapshot Jobs |
