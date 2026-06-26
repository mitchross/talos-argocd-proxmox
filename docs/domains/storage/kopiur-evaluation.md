# kopiur evaluation — engine candidate for the backup path

> Strategic companion to the operational [`docs/kopiur-trial.md`](../../kopiur-trial.md).
> Captures the 2026-06-26 evaluation of **kopiur** (home-operations' Kopia-native
> Rust backup operator) as a possible pvc-plumber/VolSync replacement: the fit
> analysis, the community landscape, the maintainer conversation, the source-code
> map, and the verified facts. Decision + trial status at the top.

## TL;DR decision
- **kopiur is a backup ENGINE + CRD API — effectively a VolSync replacement, NOT a pvc-plumber replacement.** pvc-plumber is a DX + governance layer (3 labels → generated `RS`/`RD`, `/audit` ledger, `needs-human-review`). kopiur has no equivalent DX/audit layer.
- **The restore-before-bind "hold" is the Kubernetes Volume Populator contract** — provided by VolSync today and by kopiur's `Restore` populator. It is *not* a pvc-plumber feature; pvc-plumber only generates the VolSync objects. Confirmed verbatim (k8s docs): *"the PVC doesn't bind to the PV until it's fully populated… pods won't begin running until everything is ready."*
- **Don't rip-replace pvc-plumber with kopiur.** You'd lose labels + `/audit` and adopt a pre-1.0 alpha. If you want kopiur's engine, keep a thin label→CRD layer on top (pvc-plumber, or a Kustomize/Helm component). The maintainer confirmed kopiur stays explicit by design ("own your PVC, use `existingClaim`"), so the convenience/safety layer is yours to own.
- **Status:** trialing on the **karakeep** canary via PR #1489 (branch `claude/kopiur-trial`). See [`kopiur-trial.md`](../../kopiur-trial.md).

## The 5-question fit comparison

| # | Requirement (what pvc-plumber gives) | kopiur reality | Verdict |
|---|---|---|---|
| 1 | **Restore-before-bind** on recreate | Implemented (`target.populator` handshake, v0.4.7). PVC stays `Pending` until restored; `onMissingSnapshot: Continue` = restore-if-exists-else-fresh, `Fail` = hard stop. | ✅ **parity** (same K8s populator contract) |
| 2 | **Zero-YAML, label-driven** backend | None. Explicit `SnapshotPolicy`+`SnapshotSchedule`+`Restore` per PVC (a `pvcSelector` covers multiple but you still author CRs). | ❌ **gap** — kopiur's core is the opposite |
| 3 | **`/audit` ledger of the negative space** + exemptions | metrics/`doctor`/`status` report on kopiur's *own* resources only. No PVC-coverage map, no `needs-human-review`, no exemption-reason. Unconfigured PVCs are invisible. | ❌ **gap** |
| 4 | **Node-local mover** (data gravity) | Per-PVC mover Job co-located on the PVC's node; Rust binary + kopia, ~70 MB. Controller never pulls data centrally. | ✅ **parity** — but bytes still move via **kopia**; "Rust" wins the *control plane*, not network throughput |
| 5 | **Permissive blast radius** (operator down ≠ outage) | Validating+mutating webhooks, default `failurePolicy: Fail` — but rules target **only `kopiur.home-operations.com` CRDs**, never PVCs/Pods. App deploy is never blocked. | ⚠️ **not permissive, but ≪ your old PVC webhook**; only the DR `Restore`-CR path is gated (mitigate: early sync wave / `failurePolicy: Ignore`) |

## Community landscape — who actually does restore-before-bind

| Tool | Label/annotation-driven | Hold PVC until restored (populator) | Fit |
|---|---|---|---|
| **VolSync** | ❌ (you template `RS`/`RD`) | ✅ yes (`dataSourceRef → ReplicationDestination`) | the engine you run today; mature (`v0.16.0`, backube) |
| **kopiur** | ❌ (explicit CRDs) | ✅ yes (`dataSourceRef → Restore`) | alpha (`0.4.x`, daily releases, AGPL, PRs declined) |
| **Velero** | ✅ | ❌ restore is a separate step | reintroduces the blank-PVC race |
| **K8up / Stash / Gemini** | ✅ | ❌ | backup-only / annotation-triggered delete+replace |

**Only VolSync and kopiur implement the populator-hold.** Everything else backs up fine but restores as a separate imperative step — exactly the blank-PVC-then-corrupt race this whole system exists to prevent.

## Why "just restore afterward" is not enough
The hold matters because restore-after-the-fact is often **too late** — a one-way door once the app boots on an empty volume:
1. **The good snapshot can already be gone** — the blank instance's *own* scheduled backup snapshots the empty state; retention ages out the real one. "Restore" then restores the blank.
2. **Irreversible external side effects** — re-onboarding mints/rotates API keys + tokens (provider revokes the old ones). Restoring the old DB brings back revoked creds and drops the new ones — broken either way. (e.g. Sonarr's API key embedded across Prowlarr/Overseerr; HA OAuth tokens.)
3. **Divergent writes** — the app wrote real data to the blank volume (moved files, queued work, new history); restoring the old DB loses it *and* desyncs from disk.
4. **Lockout deadlock** — for auth-bearing apps (Vaultwarden, an IdP) the credential lived in the data you lost; "log in again" assumes a login that no longer exists.

Sharpest example (used in the maintainer pitch): a **game-server world save** (Minecraft/Valheim/Zomboid) — irreplaceable, no "login," and the fresh-world backup overwrites the real one.

## Maintainer conversation (home-operations Discord, 2026-06-26)
Raised the GitOps "blank-PVC on recreate" problem as a question (not a pitch). Outcome:
- bo0tzz (maintainer): the populator-hold is **the default behavior** when the PVC carries `dataSourceRef`. *"The whole concept of letting a chart own an important PVC is scary to me."*
- m00n: *"just don't let the chart make the PVC, set it to an existing PVC"* (i.e. `existingClaim` + you own the PVC) — community-upvoted.
- **Conclusion:** kopiur is **intentionally explicit** (own your PVC, wire `Restore`+`dataSourceRef` yourself). It will **not** own a label-driven auto-wiring / audit layer — same instinct that makes the maintainer dislike implicit PVC magic. **So that convenience+safety layer stays yours** (pvc-plumber, or a thin Kustomize/Helm component). The residual real gap: at ~30 hand-owned PVCs, *forgetting* the `dataSourceRef`/`Restore` on one is silent until a rebuild — which is exactly what a label-stamp prevents.

## kopiur source map (Rust, `kube-rs`)
The auto-hydrate mechanics **already exist**; the only missing piece is a label→`Restore`+`dataSourceRef` trigger, and `dataSourceRef` immutability constrains where it can live.

| Capability | File : function |
|---|---|
| Populator handshake (pause-bind → prime PVC → rebind) | `crates/controller/src/restore/mod.rs` : `drive_populator_restore` → `ensure_prime_pvc` → `run_restore_mover` → `rebind_prime_to_consumer` → `finalize_populator` |
| Snapshot resolution + `onMissingSnapshot` (`Continue`→`Empty`, `Fail`→`Failed`) | `restore/mod.rs` : `reconcile` / `resolve_snapshot`; `restore/plan.rs` : `populator_state` |
| "Does a backup exist for this volume?" (by identity) | `crates/kopia/src/client/mod.rs` : `snapshot_list(filter)`; pick latest via `selection.rs` : `pick_offset` |
| Execute restore | `kopia/src/client/mod.rs` : `snapshot_restore` / `snapshot_restore_with` |
| **Trigger seam** for a label-driven mapper | `crates/controller/src/watch.rs` : `pvc_to_restores` (today matches `spec.dataSourceRef`); model a `pvc_labels_to_restores` on the existing selector mapper `policy_to_schedules` |
| Webhook (CRD-only) | `crates/webhook/src/handlers.rs` : per-CRD handlers; **only `Snapshot` mutates**; **no PVC/Pod handler** |

**The architectural constraint:** `dataSourceRef` is immutable and must exist **at PVC create time** (it's what makes K8s withhold binding). A label on a *bare* PVC can't trigger the hold — by the time a controller sees it, the default StorageClass already bound it empty. So label→`dataSourceRef` must happen at **render/admission time**, not in a post-bind controller. A PVC mutating webhook would do it but (a) breaks kopiur's CRD-only webhook scope, (b) puts a synchronous S3 check in the admission path (anti-pattern), (c) `failurePolicy` on PVCs is the exact SPOF pvc-plumber removed. **Design-compatible answer: render-time generation** (a `kubectl kopiur` / Helm-template helper, or pvc-plumber) — Git carries the `dataSourceRef`.

## Verified kopiur facts (as of `0.4.13`, 2026-06)
- **OCI chart published** at `oci://ghcr.io/home-operations/charts/kopiur` (upstream `release.yaml` does `helm package … --app-version=$VERSION` → `helm push … oci://ghcr.io/home-operations/charts`, so **chart version == app version**, e.g. `0.4.13`). Render it locally via Kustomize `helmCharts:` (`infrastructure/controllers/kopiur-operator/`) like every other chart in this repo — manifests come from our own git source, so **no AppProject `sourceRepos` exception is needed**. (The in-repo `deploy/helm/kopiur/Chart.yaml` carries an internal `0.1.0`; the published OCI artifact is re-versioned per release. Tags carry no `v` prefix.)
- **CRDs (`v1alpha1`):** `Repository`, `ClusterRepository`, `SnapshotPolicy`, `Snapshot`, `SnapshotSchedule`, `Restore`, `Maintenance`, `RepositoryReplication`. (ADR-0003 still calls them `BackupConfig`/`Backup`/`BackupSchedule` — renamed; expect more CRD churn pre-1.0.)
- **S3 backend:** `backend.s3.{bucket, prefix, endpoint, region}`, `endpoint` is a **bare `host:port`** (no scheme/slash), TLS-off is `tls.disableTls: true`. `ClusterRepository` secret refs **must** carry an explicit `namespace` (webhook-enforced).
- **Creds Secret keys:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `KOPIA_PASSWORD`.
- **Chart values:** `installScope` (`namespaced`|`cluster`), `installCRDs: true` (default), `webhook.failurePolicy: Fail` (default), `webhook.tls.mode: self` (self-signs at runtime — **no cert-manager hook Job**, ArgoCD-safe), per-image `image.{controller,webhook,mover}.tag/digest`.
- **Mover:** statically-linked Rust binary + official kopia binary, distroless ~70 MB; reads a downward-API JSON work spec, streams `kopia --json`, PATCHes progress to `status`. Co-locates on the PVC's node for RWO (avoids Multi-Attach).
- **Backend-down safety differs from ours:** kopiur uses a repository health-probe / preflight, **not** the `wait-for-rustfs` MutatingAdmissionPolicy (which only gates VolSync mover Jobs). Verify kopiur's preflight actually blocks a snapshot Job when RustFS is unreachable before trusting it.

## Reference implementations (other clusters running kopiur)
Two real-world Flux adoptions cross-checked our manifests and corrected several fields:
- **onedr0p/home-ops #11012** ("chore: deploy kopiur", chart `0.2.0`) — installs the operator via an **OCI Helm chart** (`oci://ghcr.io/home-operations/…`, image digests pinned), a `ClusterRepository`, and a **reusable `components/kopiur` component** (SnapshotPolicy + SnapshotSchedule + deploy-or-restore PVC + passive Restore) composed per-app via `components:` + postBuild `APP=<app>`. Centralized mover defaults + `ttlSecondsAfterFinished`. Its migration steps match our drill (verify a Snapshot succeeded with non-zero files → scale down → delete PVC → reapply → populator hydrates → scale up).
- **eleboucher/homelab** `garage/app/kopiur.yaml` — single-app form; confirmed the field shapes our first cut was missing.

**Fields these corrected in our karakeep manifests (now applied):**
| Field | Why it matters |
|---|---|
| `copyMethod: Snapshot` + `volumeSnapshotClassName: longhorn-snapclass` | CSI snapshots won't fire on Longhorn without them |
| `credentialProjection.enabled: true` (policy + restore) | the mover in the app namespace can't reach the ClusterRepository creds otherwise |
| `mover.securityContext {runAsUser/runAsGroup: 568}` + `mover.podSecurityContext.fsGroup: 568` | restored files get wrong ownership (karakeep is 568). **`fsGroup` is pod-level — it lives under `mover.podSecurityContext`, NOT `mover.securityContext`** (the latter is the container SC and rejects `fsGroup` under strict CRD validation; caught live 2026-06-26 via SSA typed-patch). kopiur can also `mover.inheritSecurityContextFrom` a workload |
| Restore `source.fromPolicy` (vs `identity`) | simpler; what both reference repos use |
| Schedule `concurrencyPolicy: Forbid` | no overlapping snapshot Jobs |

- **Operator-install hint:** both use the **OCI chart** (`oci://ghcr.io/home-operations/charts/kopiur`). ✅ **Adopted** — we now render that OCI chart via Kustomize `helmCharts:` (`infrastructure/controllers/kopiur-operator/`), matching the rest of the repo and dropping the git-tag render + the AppProject whitelist it required.
- **DX hint:** onedr0p's reusable component is the Flux analog of the Kustomize component to build for ArgoCD — stamp the whole bundle from ~2 values instead of hand-writing per PVC.

## Open items / next steps
1. **Verify CRD field shapes** against the installed `0.4.13` chart (`kubectl explain`) — assembled here from upstream `main` examples.
2. **Run the restore-before-bind drill** on karakeep (delete `data-pvc` → confirm `Pending` → restore → `Bound` with data). See `kopiur-trial.md`.
3. **Decide:** replace vs hybrid vs keep. Current lean — **keep pvc-plumber + VolSync**; revisit kopiur as an engine swap *under* a thin label layer once it's past 1.0 / stops churning CRDs.
4. If hybridizing: a Kustomize/Helm component that stamps `SnapshotPolicy`+`Schedule`+`Restore`+`dataSourceRef` from ~3 values restores the DX without the operator.
5. Optional upstream **issue** (not PR — they're declined): `Restore`-scoped `failurePolicy` so DR isn't gated by operator cold-start.
