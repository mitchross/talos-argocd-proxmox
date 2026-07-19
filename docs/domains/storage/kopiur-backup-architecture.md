# kopiur backup architecture — the instruction manual

> How the pieces fit together for backup **and** restore, and which part lives
> where. If you're new to Kustomize **components**, start at §2 — that's the bit
> that trips people up. Permissions deep-dive: [`kopiur-mover-permissions.md`](kopiur-mover-permissions.md).

kopiur is the cluster's backup system: a Kopia-native operator. You declare small
CRs, it runs Jobs, kopia moves bytes to RustFS.

![Kopiur Kustomize assembly, backup, and restore-before-bind flow](../../assets/kopiur-kustomize-flow.svg)

*The app stub owns what varies per PVC; the shared Component adds cluster-wide
defaults. Kustomize renders complete resources for Argo CD, and those resources
drive both the scheduled backup and restore-before-bind paths.*

[Open the full-size diagram](../../assets/kopiur-kustomize-flow.svg)

## Lifecycle and Flows

<div class="grid cards" markdown>

-   **1. GitOps & Kustomize Assembly**

    `Build time`

    1. The **app stub** declares the policy, schedule, restore target, and mover
       UID:GID.
    2. The shared **kopiur component** adds the repository, copy method, and
       volume-populator settings.
    3. **ArgoCD** combines both with Kustomize and applies the rendered resources
       to Kubernetes.

-   **2. Scheduled Backup**

    `Runtime`

    1. A **SnapshotSchedule** creates a Snapshot custom resource.
    2. The **kopiur operator** takes a Longhorn CSI snapshot and starts a mover
       Job as the data owner.
    3. The mover reads S3 credentials from `kopiur-rustfs` and uploads encrypted,
       deduplicated data to `s3://kopiur`.

-   **3. Restore Before Bind**

    `Disaster recovery`

    1. **ArgoCD** recreates a PVC that references a kopiur Restore.
    2. Kubernetes keeps the PVC `Pending` while the **restore populator** starts
       a mover Job.
    3. The mover restores data from RustFS; only then does Kubernetes bind the
       PVC and start the application.

</div>

---

## 1. The pieces (what exists, and where)

**Cluster-wide — set up once**

- `infrastructure/controllers/kopiur/` defines the `cluster-kopia` repository,
  the `kopiur-rustfs` credential fanout, and `longhorn-snapclass`.
- The operator in `kopiur-system` watches kopiur resources and runs snapshot and
  restore Jobs.
- `my-apps/common/kopiur-backup/` holds the shared Kustomize component.

**Per app — add for every protected PVC**

- Label `namespace.yaml` to receive repository credentials.
- Point `pvc.yaml` at the Restore with `dataSourceRef`.
- Add the `kopiur/<pvc>.yaml` stub.
- Include the stub under `resources:` and the shared component under
  `components:` in `kustomization.yaml`.

| Piece | Scope | What it does |
|---|---|---|
| `ClusterRepository cluster-kopia` | cluster | the kopia repo definition → RustFS `s3://kopiur` |
| `ClusterExternalSecret kopiur-rustfs` | cluster | fans the repo creds into any namespace labeled `kopiur.home-operations.com/repo: cluster-kopia` |
| `VolumeSnapshotClass longhorn-snapclass` | cluster | how CSI snapshots are taken (Longhorn) |
| kopiur operator | cluster | reconciles the CRs; launches the mover Jobs |
| **component** `common/kopiur-backup` | shared | injects the **uniform** fields into your stub |
| **stub** `kopiur/<pvc>.yaml` | per-PVC | the **varying** bits: name, identity, cron, **mover UID** |
| namespace label | per-app | turns on creds + repo access for that namespace |
| PVC `dataSourceRef` | per-PVC | wires restore-before-bind to the `Restore` |

---

## 2. How a Kustomize component composes (read this if components are new)

A **component** is a reusable bundle of patches. Your app's `kustomization.yaml`
"pulls it in" with `components:`. At build time Kustomize takes the resources you
list, then lets the component **patch** them. So the per-PVC stub stays tiny (just
the bits that differ); the component fills in everything that's the same for every
backup.

In plain English: the app explicitly opts into the Component. Kustomize loads the
app's resources, finds the Kubernetes objects targeted by the Component, adds the
shared fields in memory, and prints complete YAML. Argo CD then compares and
applies that rendered YAML.

Kustomize parses the YAML into structured Kubernetes objects, matches the
Component patches to resources by API group and kind, applies JSON Patch
operations to exact object paths such as `/spec/repository`, and serializes the
result as complete YAML. Neither source file is rewritten. Components are a
first-class Kustomize feature intended to package reusable, opt-in configuration,
not a repository workaround ([upstream Components example](https://github.com/kubernetes-sigs/kustomize/blob/master/examples/components.md)).

It does **not** automatically run because a certain filename exists. The app's
`kustomization.yaml` is the build entrypoint and must explicitly list the
Component under `components:`. The Component then sees the resources accumulated
by that app and transforms matching objects. It is not a parent manifest and it
does not run independently.

### Is this like Kyverno?

No. The outcome can look similar because both tools can add fields, but they run
at different times and own different boundaries:

| Kustomize Component | Kyverno policy |
|---|---|
| Runs during `kustomize build`, before submission | Runs inside the cluster during admission/background reconciliation |
| Explicitly included by an app's `components:` list | Watches API requests or existing cluster resources |
| Produces the desired YAML that Argo CD compares and applies | Validates or mutates resources as they enter or live in the cluster |
| No controller remains running for the Component | Kyverno controllers must remain running |

With Argo CD, the actual path is:

```text
Git files -> Argo CD repo-server -> kustomize build
          -> rendered YAML -> Argo CD diff/apply -> Kubernetes API
```

`kubectl apply -k <app>` performs the same build-then-apply sequence locally.

Conceptually, the build does this:

```javascript
function applyKopiurComponent(resource) {
  // Kustomize works on parsed objects, not raw text or filenames.
  const output = structuredClone(resource);

  const isSnapshotPolicy =
    output.apiVersion.startsWith("kopiur.home-operations.com/") &&
    output.kind === "SnapshotPolicy";

  if (isSnapshotPolicy) {
    output.spec.copyMethod = "Snapshot";
    output.spec.volumeSnapshotClassName = "longhorn-snapclass";
    output.spec.repository = {
      kind: "ClusterRepository",
      name: "cluster-kopia",
    };
  }

  return output;
}

const appResources = loadResourcesFromKustomization();
const renderedResources = appResources.map(applyKopiurComponent);

printYaml(renderedResources); // this is what Argo CD applies
```

That JavaScript is only a teaching model. Real Kustomize uses the Component's
target selector and JSON Patch operations, but the data flow is equivalent.
Non-matching resources pass through unchanged, and the source YAML files are not
rewritten.

![A per-PVC stub and reusable Kustomize Component combine into a complete SnapshotPolicy](../../assets/kustomize-component-mixin.svg){ loading=lazy }

*Coral fields belong to the application. Green fields are shared defaults from
the Component. The rendered resource contains both before Argo CD sees it.*

[Open the full-size Component diagram](../../assets/kustomize-component-mixin.svg)

### Why use it here?

Every protected PVC needs the same repository, snapshot class, copy method,
restore populator, and scheduling safety defaults. Repeating those fields in
every app would make drift likely and a cluster-wide change tedious. The
Component makes those settings one shared policy while each app still owns its
identity, retention, schedule, and mover UID.

The trade-off is visibility: the stub is not the complete deployed object when
read by itself. Use `kubectl kustomize <app>` to inspect the real output. Keep
varying fields out of the Component, keep targets narrow, and render every app in
CI. In this repository the Component intentionally affects every matching
`SnapshotPolicy`, `SnapshotSchedule`, and `Restore` included by that one app's
Kustomization; it cannot reach resources in another Argo CD Application.

```yaml
resources:
  - namespace.yaml
  - pvc.yaml
  - kopiur/<pvc>.yaml
components:
  - ../../common/kopiur-backup
```

Read that as: "load these resources, opt into these shared transformations,
then print the combined result."

| Resource | App stub supplies | Component adds |
|---|---|---|
| `SnapshotPolicy` | name, source PVC, identity, retention, mover UID:GID | repository, `copyMethod: Snapshot`, `volumeSnapshotClassName` |
| `SnapshotSchedule` | cron schedule | `concurrencyPolicy: Forbid`, `runOnCreate: false` |
| `Restore` | source policy, mover UID:GID | repository, `target.populator`, `onMissingSnapshot: Continue` |

`kubectl kustomize <app>` combines both sets of fields into the complete custom
resources that ArgoCD applies.

**Keep the mover UID in the stub, not the component:** it varies per PVC (the
data owner differs app to app — even within one namespace), and a component
patches *all* resources of a kind the same way, so it can't set a per-PVC value.
The component sets only what's identical everywhere.

---

## 3. Backup flow (what happens on a schedule)

1. A `SnapshotSchedule` fires on its cron, for example `10 3 * * *`, and creates
   a Snapshot custom resource.
2. The kopiur operator creates a point-in-time CSI `VolumeSnapshot` through
   `longhorn-snapclass`.
3. The operator launches a mover Job as the data owner UID:GID and mounts the
   snapshot read-only.
4. The mover reads S3 credentials from the local `kopiur-rustfs` Secret, which
   the `ClusterExternalSecret` placed in the namespace.
5. Kopia uploads deduplicated, encrypted data to RustFS at `s3://kopiur`, then
   marks the Snapshot `Succeeded` with its file and byte counts.

The mover must run as the **data owner** or it can't read the files — see
[`kopiur-mover-permissions.md`](kopiur-mover-permissions.md).

A backup against an unreachable repo errors: the Snapshot Job fails and retries,
nothing garbage is written.

---

## 4. Restore-before-bind flow (the DR magic)

The whole point: when a PVC is recreated, it does **not** come up empty — it
holds at `Pending` until kopiur restores its data, *then* binds.

1. ArgoCD recreates the PVC from Git after a PVC deletion, namespace recreation,
   or full disaster recovery.
2. The PVC's `dataSourceRef` points to `<pvc>-restore`, so Kubernetes withholds
   binding and leaves the PVC `Pending`.
3. The kopiur restore populator checks the repository and decides how to proceed.

| Repository state | Result |
|---|---|
| Reachable, snapshot exists | A mover restores the data, the PVC binds, and the pod starts. |
| Reachable, no snapshot yet | `onMissingSnapshot: Continue` binds an empty PVC, which backs up forward. |
| Unreachable | The restore errors and retries; the PVC stays `Pending` and never binds empty. |

> A restore against an unreachable repo leaves the PVC `Pending` — kopiur raises
> the backend error *before* the "no snapshot → empty" decision, so an outage can
> never bind an empty volume. (Source: `crates/controller/src/restore/mod.rs`
> `resolve_snapshot`.) `onMissingSnapshot: Continue` means a brand-new PVC with a
> *reachable* repo but no snapshot still binds empty and backs up forward —
> deploy-or-restore in one path.

---

## 5. To add a backup (checklist)

1. `kubectl -n <ns> exec <pod> -- stat -c '%u:%g' <data-mountpath>` → note the **owner uid:gid**.
2. Namespace: add label `kopiur.home-operations.com/repo: cluster-kopia` (+ the
   `privileged-movers` annotation only if owner is `0`).
3. Add `kopiur/<pvc>.yaml` stub (SnapshotPolicy + Schedule + Restore) with the
   mover set to that uid:gid; pick a distinct cron minute — check **both**
   tiers: an hourly `MM * * * *` occupies minute MM of *every* hour, so a
   daily `MM 3 * * *` with the same MM collides at 03:MM (caught in the
   2026-07-04 audit: mysql 03:25 vs meilisearch hourly :25). List the taken
   minutes before picking:
   ```bash
   grep -rh 'cron:' my-apps/*/*/kopiur* my-apps/*/*/*/kopiur* | sort
   ```
4. PVC: `dataSourceRef -> Restore/<pvc>-restore` + the two `ServerSide*` annotations
   (`argocd.argoproj.io/compare-options: ServerSideDiff=false` and
   `argocd.argoproj.io/sync-options: ServerSideApply=false` — the immutable-`dataSourceRef` diff mask).
   **Retrofitting a running app?** Expected: ArgoCD shows a
   `PVC is invalid: Forbidden` ComparisonError — `dataSourceRef` is immutable
   on a Bound PVC. Harmless: backups start immediately anyway, and the
   `dataSourceRef` arms on the next recreate (which is exactly what DR is).
   The annotations + AppSet `ignoreDifferences` mask the diff.
5. Kustomization: add the stub to `resources:` and `../../common/kopiur-backup` to `components:`.
6. Verify: `kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore,snapshot,secret`.

Copy from [`my-apps/ai/open-webui/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/ai/open-webui) (simple)
or [`my-apps/home/project-nomad/mysql/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/my-apps/home/project-nomad/mysql)
(daemon-drop uid `999:568`). Full step-by-step: [`.claude/commands/add-backup.md`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/.claude/commands/add-backup.md).

---

## 6. Upstream 0.5.x–0.7 notes (assessed 2026-07-04, updated 2026-07-07, chart pinned `0.7.0`)

What changed upstream in 0.5.0–0.7.0 and how it lands here:

- **0.7.0 = a trivial bump for us** (2026-07-07). The chart's `values.yaml` is
  byte-identical to 0.6.0, the `kubeVersion` floor is unchanged (`>=1.32.0-0`),
  and the CRD set is the same 8. Its breaking changes are all internal Rust
  dependency upgrades (kube 4.0, croner 3.0, reqwest/rand) plus the
  `RepositoryReplication` sync-to credential fix (#200) — which we don't use
  (no replication). Render-verified with our values: 20 objects, images at
  `0.7.0`, `failurePolicy: Ignore` intact.
- **0.5.2: transient VolumeSnapshot errors are retried, not terminal** (#201).
  Before, a Longhorn hiccup during CSI staging burned the whole backup run.
- **Failed `Snapshot` CRs are terminal by design** — kopiur never retries a
  failed run in place; the **next cron fires a fresh Snapshot** (partial
  uploads in the Kopia repo are reused, so retries are cheap). Failed CRs are
  pruned at `failedJobsHistoryLimit` (default 10). A staging hang fails at
  `spec.staging.timeout` (default 10m, reason `StagingTimedOut`).
- **`inheritSecurityContextFrom: pvcConsumer: {}`** exists as an alternative to
  hand-set mover uids — we deliberately DON'T use it: bjw-s reported it
  detecting the wrong consumer uid intermittently, and during a DR cold-start
  restore there is **no consumer pod to inherit from**. Explicit
  data-owner uids in the stubs stay the rule
  (`kopiur-mover-permissions.md`).
- **0.6.0 = the breaking chart refactor** (#203 → #206), bumped here
  2026-07-06. Our values keys (`installScope`, `webhook.failurePolicy`,
  `webhook.tls.mode`) kept their paths; the inert `installCRDs` line was
  deleted; images follow appVersion as before. New in the render: a
  leader-election Role/RoleBinding — benign.
  **⚠️ The upgrade that burned everyone else:** CRDs moved from templated
  chart resources to Helm's native `crds/` dir, and Helm does NOT manage
  `crds/` on upgrade — Flux HelmRelease users had the old templated CRDs
  **deleted on upgrade, taking every kopiur CR with them**, then had to
  force-reconcile them back (upstream Discord, 2026-07-06). **This repo's
  render path is immune**: Kustomize runs `helm template --include-crds`,
  which emits the same 8 CRDs before and after the move, so ArgoCD never
  sees them leave the manifest (CRD-set continuity render-verified at the
  bump). The load-bearing line is `includeCRDs: true` in
  `kopiur-operator/kustomization.yaml` — never remove it.
  Second 0.6.0 gotcha, caught by CI: the chart's `kubeVersion` floor rose to
  `>=1.32.0-0`, and `kustomize build --enable-helm` (CI **and** the ArgoCD
  repo-server) templates with helm's default capabilities (v1.31) unless the
  helmCharts entry sets `kubeVersion:` — added, pointing at the real cluster
  version. Any future chart with a kubeVersion constraint needs the same.

- **`copyMethod` now defaults to `Snapshot` upstream** (was `Direct`). We were
  already pinning `Snapshot` via the component — **keep the explicit pin**:
  upstream warns a server-defaulted field has no SSA field owner, so a GitOps
  re-apply of a manifest that *omits* the field can silently flip it on a CRD
  upgrade. Explicit value = owned field = immune. (Comment lives on the patch
  in `my-apps/common/kopiur-backup/kustomization.yaml`.)
- **`verification.quick` reshaped** to `{ schedule: { cron, jitter, timezone } }`
  (was a bare `{ cron, jitter }`). We don't use `verification` yet; if you add
  it, use the nested shape — the old shape is rejected on new writes.
  Verification is also now **gated on a verifiable snapshot existing** (no more
  verify-Job-fails-against-empty-repo on a fresh policy).
- **Metrics renamed / store-backed** (`kopiur_snapshot_*` →
  `kopiur_policy_last_backup_*`; `kopiur_resource_phase` emits active-only
  series). Irrelevant here today: the chart's ServiceMonitor/PrometheusRule/
  dashboard are all disabled and nothing in `monitoring/` scrapes kopiur metric
  names. If you ever enable scraping, use the new names.
- **`scheduleDefaults.timezone`** can now be set once on the
  `ClusterRepository` and every cron (backup schedules, verification,
  maintenance) inherits it. We deliberately stay on UTC — setting it would
  shift every existing schedule slot.
- **`failedJobsHistoryLimit`** on `SnapshotSchedule` (default 10) bounds failed
  `Snapshot` CRs; *succeeded* ones are pruned by the policy's GFS `retention` —
  which is why **every SnapshotPolicy must set `retention`** (audit-verified:
  all 22 do).
- **`files.ignoreRules` defaults** to OS-artifact junk (`/lost+found`,
  `System Volume Information`, `$RECYCLE.BIN`, `@eaDir`, `.snapshot`) — free
  win, no action.
- **`kubectl kopiur` CLI shipped in 0.5.1** (krew + Homebrew). Friendliest
  debugging surface for backup state — worth installing on workstations:
  `kubectl krew install kopiur`, then `kubectl kopiur --help`.
- **`credentialProjection` is heading for removal** (maintainer is migrating
  off it upstream). We never used it — the ESO `ClusterExternalSecret` fanout
  in `infrastructure/controllers/kopiur/externalsecret.yaml` is exactly the
  replacement pattern upstream recommends — so the eventual removal is a
  no-op here.
- **Known upstream race (#194):** in a namespace with the `privileged-movers`
  annotation, the grant event can be missed when namespace + CRs land together
  (DR cold-start), leaving `MoverPermitted=False` until a ~5 min backstop.
  Only the three root-mover namespaces (home-assistant, tubesync,
  nginx-example) qualify; the nudge is any no-op metadata touch on the CR.
  See the DR runbook.
- **Least-privilege reminder:** the `privileged-movers` annotation belongs
  ONLY on namespaces whose mover is elevated (uid 0, `runAsNonRoot: false`,
  added caps, or `privilegedMode`). The 2026-07-04 audit stripped it from 15
  namespaces where it had been blanket-copied during the VolSync migration.
