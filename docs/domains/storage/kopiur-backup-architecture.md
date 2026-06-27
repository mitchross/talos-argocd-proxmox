# kopiur backup architecture — the instruction manual

> How the pieces fit together for backup **and** restore, and which part lives
> where. If you're new to Kustomize **components**, start at §2 — that's the bit
> that trips people up. Permissions deep-dive: [`kopiur-mover-permissions.md`](kopiur-mover-permissions.md).

kopiur replaced pvc-plumber + VolSync (retired 2026-06-27). It is a Kopia-native
operator: you declare small CRs, it runs Jobs, kopia moves bytes to RustFS.

---

## 1. The pieces (what exists, and where)

```
 CLUSTER-WIDE (set up once)                          PER APP (you add these)
 ──────────────────────────                          ───────────────────────
 infrastructure/controllers/kopiur/                  my-apps/<cat>/<app>/
   • ClusterRepository  "cluster-kopia"                • namespace.yaml   (1 label)
       └─ points at RustFS  s3://kopiur                • pvc.yaml         (dataSourceRef)
   • ClusterExternalSecret "kopiur-rustfs"             • kopiur/<pvc>.yaml (the STUB)
       └─ copies repo creds into labeled namespaces    • kustomization.yaml
   • VolumeSnapshotClass "longhorn-snapclass"              └─ components: [kopiur-backup]
                                                            └─ resources:  [kopiur/<pvc>.yaml]
 kopiur operator (kopiur-system)
   • watches the CRs, runs Snapshot/Restore Jobs      my-apps/common/kopiur-backup/
                                                        • the shared COMPONENT (no app owns it)
```

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

```
 my-apps/<cat>/<app>/kustomization.yaml
   resources:
     - namespace.yaml            label: kopiur.home-operations.com/repo=cluster-kopia
     - pvc.yaml                  spec.dataSourceRef -> Restore "<pvc>-restore"
     - kopiur/<pvc>.yaml  ◄───── YOUR STUB (varying bits ONLY):
   components:                       SnapshotPolicy  { name, sources.pvc, identity, retention, MOVER uid:gid }
     - ../../common/kopiur-backup    SnapshotSchedule{ cron }
              │                      Restore         { fromPolicy, MOVER uid:gid }
              │
              └── patches by KIND, adds the UNIFORM fields:
                    SnapshotPolicy += repository: cluster-kopia, copyMethod: Snapshot,
                                      volumeSnapshotClassName: longhorn-snapclass
                    SnapshotSchedule += concurrencyPolicy: Forbid, runOnCreate: false
                    Restore += repository, target.populator:{}, onMissingSnapshot: Continue

   $ kubectl kustomize <app>     ─────►   FULL CRs  =  (your stub fields)  +  (component fields)
```

**Why the mover UID is in the stub, not the component:** it varies per PVC (the
data owner differs app to app — even within one namespace), and a component
patches *all* resources of a kind the same way, so it can't set a per-PVC value.
The component sets only what's identical everywhere.

---

## 3. Backup flow (what happens on a schedule)

```
 SnapshotSchedule (cron, e.g. "10 3 * * *")
        │  fires
        ▼
   Snapshot CR ──────────────► kopiur operator
                                   │
                                   ├─ 1. CSI VolumeSnapshot (longhorn-snapclass)
                                   │        └─► Longhorn point-in-time snapshot of the PVC
                                   │
                                   └─ 2. MOVER Job   (runs as the DATA OWNER uid:gid)
                                          • mounts the snapshot, read-only
                                          • reads creds from local Secret "kopiur-rustfs"
                                          │        (put there by the ClusterExternalSecret)
                                          ▼
                                        kopia ──upload──► RustFS  s3://kopiur
                                          (deduplicated + encrypted)
                                          ▼
                                        Snapshot → Completed (files, bytes)
```

The mover must run as the **data owner** or it can't read the files — see
[`kopiur-mover-permissions.md`](kopiur-mover-permissions.md).

---

## 4. Restore-before-bind flow (the DR magic)

The whole point: when a PVC is recreated, it does **not** come up empty — it
holds at `Pending` until kopiur restores its data, *then* binds.

```
 PVC deleted  /  namespace recreated  /  full DR
        │
        ▼
 ArgoCD recreates the PVC from git   (spec.dataSourceRef -> Restore "<pvc>-restore")
        │
        ▼
 Kubernetes sees a populator dataSourceRef  ──►  withholds binding   (PVC = Pending)
        │
        ▼
 kopiur Restore populator decides:
   ├─ repo reachable + snapshot exists ─► MOVER Job restores ─► PVC Binds WITH data ─► pod starts ✅
   ├─ repo reachable + NO snapshot yet  ─► onMissingSnapshot: Continue ─► binds EMPTY, backs up forward
   └─ repo UNREACHABLE                  ─► errors + retries ─► stays Pending, never empty ✅ (safe)
```

> The last line is the safety property the old `wait-for-rustfs` MAP gave us —
> kopiur preserves it for free: a backend error is raised *before* the
> "no snapshot → empty" decision, so an outage can't bind an empty volume.
> (Source-verified: `crates/controller/src/restore/mod.rs` `resolve_snapshot`.)

---

## 5. To add a backup (checklist)

1. `kubectl -n <ns> exec <pod> -- stat -c '%u:%g' <data-mountpath>` → note the **owner uid:gid**.
2. Namespace: add label `kopiur.home-operations.com/repo: cluster-kopia` (+ the
   `privileged-movers` annotation only if owner is `0`).
3. Add `kopiur/<pvc>.yaml` stub (SnapshotPolicy + Schedule + Restore) with the
   mover set to that uid:gid; pick a distinct cron minute.
4. PVC: `dataSourceRef -> Restore/<pvc>-restore` + the two `ServerSide*` annotations.
5. Kustomization: add the stub to `resources:` and `../../common/kopiur-backup` to `components:`.
6. Verify: `kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore,snapshot,secret`.

Copy from [`my-apps/ai/open-webui/`](../../../my-apps/ai/open-webui/) (simple)
or [`my-apps/home/project-nomad/mysql/`](../../../my-apps/home/project-nomad/mysql/)
(daemon-drop uid `999:568`). Full step-by-step: [`.claude/commands/add-backup.md`](../../../.claude/commands/add-backup.md).
