# kopiur evaluation: engine candidate for the backup path

> **Outcome (2026-06-27): adopted.** kopiur replaced the retired pvc-plumber +
> VolSync stack. The "thin DRY layer" recommended here shipped as the
> [`my-apps/common/kopiur-backup` Kustomize component](kopiur-backup-architecture.md#2-how-a-kustomize-component-composes-read-this-if-components-are-new).
> Current architecture: [`kopiur-backup-architecture.md`](kopiur-backup-architecture.md).

This is the 2026-06 evaluation of kopiur, home-operations' Kopia-native Rust backup operator. The file stays for the verified facts and config shapes below.

## Why kopiur

- It implements restore-before-bind through the Kubernetes Volume Populator contract. A PVC with `dataSourceRef` stays `Pending` until its `Restore` populator hydrates it, so an app never boots on an empty volume. `onMissingSnapshot: Continue` means restore if a snapshot exists, else start fresh. `Fail` means hard stop.
- kopiur is explicit by design. You own your PVC and wire `Restore` + `dataSourceRef` yourself. It ships no label-driven auto-wiring or coverage-audit layer, so we supply that layer in the `kopiur-backup` Kustomize component.
- The mover runs node-local (data gravity). A per-PVC mover Job runs on the PVC's node and streams bytes via kopia. The controller never pulls data centrally.
- Webhooks target only `kopiur.home-operations.com` CRDs, never PVCs or Pods. A kopiur outage never blocks an app deploy.

Only VolSync and kopiur implement the populator-hold. Velero, K8up, Stash, and Gemini back up fine, but they restore as a separate imperative step. That step reintroduces the blank-PVC-then-corrupt race this system exists to prevent.

### Why the hold matters (restore-after-the-fact is too late)

1. **The good snapshot can be gone.** The blank instance's own scheduled backup snapshots the empty state, and retention ages out the real one.
2. **Irreversible external side effects.** Re-onboarding rotates API keys and tokens. Restoring the old DB brings back revoked credentials (for example Sonarr, HA OAuth).
3. **Divergent writes.** The app wrote real data to the blank volume. Restoring the old DB loses that data and desyncs from disk.
4. **Lockout deadlock.** Auth-bearing apps (Vaultwarden, an IdP) lose the credential that lived in the data.

The sharpest example is a game-server world save (Minecraft, Valheim, Zomboid). It is irreplaceable, it has no login, and the fresh-world backup overwrites the real one.

## Verified kopiur facts (as of `0.5.x`, 2026-07)

- **OCI chart.** It lives at `oci://ghcr.io/home-operations/charts/kopiur`, rendered locally via Kustomize `helmCharts:` (`infrastructure/backup/kopiur-operator/`). Chart version equals app version (e.g. `0.5.1`), and tags carry no `v` prefix. Manifests come from our own git source, so no AppProject `sourceRepos` exception is needed.
- **CRDs (`v1alpha1`).** `Repository`, `ClusterRepository`, `SnapshotPolicy`, `Snapshot`, `SnapshotSchedule`, `Restore`, `Maintenance`, `RepositoryReplication`.
- **S3 backend.** `backend.s3.{bucket, prefix, endpoint, region}`. `endpoint` is a bare `host:port` (no scheme or slash). TLS-off is `tls.disableTls: true`. `ClusterRepository` secret refs must carry an explicit `namespace` (the webhook enforces this).
- **Creds Secret keys.** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `KOPIA_PASSWORD`.
- **Chart values.** `installScope` (`namespaced`|`cluster`), `installCRDs: true`, `webhook.failurePolicy: Fail`, `webhook.tls.mode: self` (self-signs at runtime, so there is no cert-manager hook Job and it is ArgoCD-safe), and per-image `image.{controller,webhook,mover}.tag/digest`.
- **Mover.** A statically linked Rust binary plus official kopia, distroless, ~70 MB. It reads a downward-API JSON work spec, streams `kopia --json`, and PATCHes progress to `status`. For RWO it runs on the PVC's node, which avoids Multi-Attach.
- **Backend-down safety.** kopiur uses a repository health probe and preflight (there is no `wait-for-rustfs` MAP anymore). A snapshot against an unreachable repo errors and retries. A restore against an unreachable repo leaves the PVC `Pending` rather than binding empty.

## Config shapes that matter (corrected against real deployments)

Cross-checked against onedr0p/home-ops (chart `0.2.0`, its reusable `components/kopiur`) and eleboucher/homelab:

| Field | Why it matters |
|---|---|
| `copyMethod: Snapshot` + `volumeSnapshotClassName: longhorn-snapclass` | CSI snapshots won't fire on Longhorn without them |
| **ClusterExternalSecret fanout** of `kopiur-rustfs` | the mover in the app namespace can't reach the ClusterRepository creds (in `kopiur-system`) otherwise. Delivered to every namespace labeled `kopiur.home-operations.com/repo: cluster-kopia`; secret name must match the repo's `secretRef.name`. Least-privilege alternative to `features.credentialProjection` (which needs cluster-wide secret create/patch RBAC) |
| `mover.securityContext {runAsUser/runAsGroup}` + `mover.podSecurityContext.fsGroup` | restored files get correct ownership. **`fsGroup` is pod-level. Set it under `mover.podSecurityContext`, NOT `mover.securityContext`** (the container SC rejects `fsGroup` under strict CRD validation) |
| Restore `source.fromPolicy` (vs `identity`) | simpler; what both reference repos use |
| Schedule `concurrencyPolicy: Forbid` | no overlapping snapshot Jobs |
