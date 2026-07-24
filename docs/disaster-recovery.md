# Disaster Recovery

> The full-cluster destroy → rebuild → restore runbook. Concepts + per-PVC
> operations live in [storage-architecture.md](storage-architecture.md); the
> backup/restore engine (**kopiur**) and its exact flows live in
> [kopiur-backup-architecture.md](domains/storage/kopiur-backup-architecture.md)
> and [kopiur-mover-permissions.md](domains/storage/kopiur-mover-permissions.md).
> Databases recover via a **separate system** — [CNPG/Barman](domains/cnpg/disaster-recovery.md) —
> while they remain on CNPG. They are migrating to plain Postgres + kopiur
> (zero-touch, same restore-before-bind as app PVCs) per the
> [plain Postgres migration doc](domains/cnpg/plain-postgres-migration.md);
> migrated databases follow the normal kopiur flow in this runbook.

![Full-cluster failure, external survivors, Talos rebuild, Argo waves, data restoration, and acceptance](assets/disaster-recovery-sequence.svg)

*Recovery is complete only after desired state, credentials, and protected data
converge and are verified. [Open the full-size DR sequence](assets/disaster-recovery-sequence.svg).*

!!! danger
    The destructive steps require explicit operator intent. This documents the
    verified path; it is not an invitation to nuke during routine maintenance.

---

## The DR model in one diagram

```text
  Dies with the cluster            Survives (off-cluster)
  -----------------------          -------------------------------
  - Longhorn volumes               - Git repo
  - every Kubernetes object        - Kopia repo (RustFS S3)
  - exempt data:                   - CNPG Barman (S3 objects)
      PostHog CH/Kafka/Redis,      - 1Password vault
      Redis, scratch
                                   - Omni/Talos machine config

  Survives ==[ bootstrap-argocd.sh + sync waves ]==> New cluster
      New cluster
        ==[ kopiur Restore populators hydrate PVCs from Kopia ]==>
      All protected data back, unattended
```

Clusters are cattle. The Kopia repository, the Git repo, and the secrets
vault are the pets. Everything between them is reconstructed automatically.

!!! warning "Longhorn runs the V1 engine — do not switch to V2"
    Interrupted rebuilds under mass-restore load corrupt V2/SPDK replica metadata
    (upstream [#13315](https://github.com/longhorn/longhorn/issues/13315),
    [#13314](https://github.com/longhorn/longhorn/issues/13314)). Stay on V1.

---

## Pre-nuke checklist

Block the nuke until every box checks — **you restore *from* these**:

- [ ] GitHub reachable; the rebuild revision **pushed** (ArgoCD pulls origin, not your working tree)
- [ ] GHCR image pulls work
- [ ] 1Password reachable; Connect token valid and recoverable off-cluster
- [ ] Cloudflare token valid and recoverable off-cluster
- [ ] RustFS/S3 endpoint reachable; access key registered on the external server; Kopia auth works
      (a past nuke proved an unregistered external credential blocks recovery even with perfect Git state)
- [ ] Talos secrets / Omni machine configs available off-cluster
- [ ] **Backups fresh**: each backed-up PVC has a recent `Succeeded` kopiur `Snapshot` you can live with — apps roll back to exactly that snapshot. Spot-check across namespaces:
      `kubectl get snapshot -A` (look at the newest per source) and confirm no `SnapshotSchedule` is wedged: `kubectl get snapshotschedule -A`.
      To top up a stale one on demand: `kubectl kopiur snapshot now --policy <name> -n <ns>` (CLI ≥0.5.1, krew)
- [ ] **No PVC lacks a snapshot it expects to restore from.** A first restore only hydrates if a Snapshot already exists (kopiur `onMissingSnapshot: Continue` binds a snapshot-less PVC *empty* and backs up forward). Confirm every PVC you intend to *restore* (not seed) shows at least one `Succeeded` Snapshot before the nuke.
- [ ] Restore canary green: recent `last-drill-result=pass`

## Rebuild sequence

```text
  omnictl cluster delete
    -> wait: machines drained, VMs gone in Proxmox
    -> omnictl apply machine classes + template validate/sync
    -> machines provision from the NEW template
    -> bootstrap-argocd.sh
    -> sync waves walk: Cilium -> Longhorn -> kopiur -> apps
    -> restore wave runs itself
```

> **Manual pre-steps before `bootstrap-argocd.sh`** — the script assumes them; the
> exact commands are `README.md` § Bootstrap, steps 4–6: **(4)** Gateway API CRDs,
> **(5)** Cilium CNI install, **(6)** pre-seed the 1Password Connect credential
> Secrets. Skip them and the new cluster has no CNI (nodes stay `NotReady`) and
> External Secrets can never start. Step 7 is the script itself.

**Ordering rule (twice-learned):** machine classes and the cluster template
are **snapshots inside Omni** — apply + sync them *before* machines
provision, or VMs are built from stale state and must be reprovisioned.

**Bootstrap rules** (proven by the 2026-06 rebuilds):

- CRDs first, controllers second, CRs third.
- Observability is **not** a core dependency — core apps must bootstrap
  without Prometheus; `kube-prometheus-stack` is the sole owner of
  `monitoring.coreos.com` CRDs.
- The **kopiur operator** lands at **Wave 2** (`infrastructure/controllers/kopiur-operator/`
  — installs the CRDs + operator + webhook); **kopiur-config** at **Wave 3**
  (`infrastructure/controllers/kopiur/` — namespace, the `ClusterRepository
  cluster-kopia` → RustFS `s3://kopiur`, and the `ClusterExternalSecret`
  credential fan-out). Databases (Wave 4) and app backups (Wave 6) follow. The
  per-PVC kopiur CRs (`SnapshotPolicy`/`SnapshotSchedule`/`Restore`) and the
  `kopiur.home-operations.com/repo: cluster-kopia` namespace label render with
  each app at Wave 6.
- Replica rebuilds stay throttled to **1/node**
  (`infrastructure/storage/longhorn/node-failure-settings.yaml`) — a mass
  restore saturates any engine on shared homelab hardware; do not raise it
  mid-bootstrap.

## What the restore wave looks like (calibrated expectations)

- Each backed-up PVC is recreated from Git with `spec.dataSourceRef → Restore
  "<pvc>-restore"`. Kubernetes withholds binding while a populator
  `dataSourceRef` is present, so the **PVC sits `Pending`** until the kopiur
  populator restores the latest Kopia snapshot, then binds **with data** and the
  pod starts. (Full flow:
  [kopiur-backup-architecture.md §4](domains/storage/kopiur-backup-architecture.md#4-restore-before-bind-flow-the-dr-magic).)
- **Backend-down is fail-safe.** If the Kopia repo is **unreachable** during a
  restore, kopiur raises the backend error before the `onMissingSnapshot` decision,
  so the PVC stays `Pending` and retries — **it never binds empty over a black-holed
  backend.** The one case that *does* bind empty is a brand-new PVC with **no
  snapshot yet** while the repo is reachable (`onMissingSnapshot: Continue` =
  deploy-or-restore) — which is why the pre-nuke checklist insists a Snapshot exists
  for anything you intend to restore.
- Restores complete in rough size order; a full wave of ~24 PVCs is roughly an hour.
- **PostHog adds ~nothing to the wave**: only `postgres-data` restores
  (~165 MB actual — seconds to hydrate). Its ClickHouse/Kafka/Redis rebuild
  empty by design; PostHog's rebuild cost is the migrate Job re-creating the
  ClickHouse schema (minutes), not data movement.
- **The API server will wobble.** etcd fsync latency inflates under
  cluster-wide restore I/O — expect intermittent `readyz` failures, slow
  kubectl, csi-sidecar leader-election restarts. It recovers between bursts;
  it is load, not failure.
- A few movers may hit cross-node attach conflicts ("volume is currently
  attached to a different node") as Jobs recreate pods — Longhorn's
  attachment reconciler clears these; the last stragglers land as load drains.
- Verdict signals that something is actually wrong: a kopiur mover Job in
  `Failed`, a `Restore` stuck without ever populating its PVC (PVC `Pending`
  long after the repo is confirmed reachable), or a `Snapshot` stuck in error.
  Watch with `kubectl -n <ns> get snapshotpolicy,snapshotschedule,restore,snapshot`.
- **Privileged-mover namespaces may lag a grant race** (upstream kopiur #194):
  in the three root-mover namespaces (home-assistant, tubesync, nginx-example)
  the controller can miss the `privileged-movers` annotation event when the
  namespace and CRs land together (exactly the DR cold-start timing) and leave
  `MoverPermitted=False` until a ~5 min backstop requeue. If a Restore there
  sits blocked well past that, nudge it: `kubectl -n <ns> annotate restore
  <name> kopiur.home-operations.com/kick="$(date +%s)"` (any no-op metadata
  touch retriggers reconcile).

## In-cluster registry and Gitea Actions

`registry.vanillax.me` is an in-cluster registry backed by cluster storage.
After a full nuke, the registry pod, Service, and HTTPRoute can all be healthy
while the registry catalog is still empty. Any workload pinned to
`registry.vanillax.me/...` will then fail with `ImagePullBackOff` until those
images are rebuilt or repushed.

Check the catalog from inside the registry pod:

```bash
kubectl exec -n kube-system deploy/registry -- \
  wget -qO- http://127.0.0.1:5000/v2/_catalog
```

Restore Gitea first, then get the Gitea Actions runner online. The runner
needs `Secret/gitea-actions/act-runner-token`; Git declares that as an
ExternalSecret and 1Password stores the generated token:

- vault: `homelab-prod`
- item: `gitea-actions`
- field: `act_runner_token`

Generate or rotate the token from the restored Gitea pod:

```bash
kubectl exec -n gitea deploy/gitea -- gitea actions generate-runner-token
```

If 1Password is not updated yet, this manual patch gets the live runner moving:

```bash
TOKEN="$(kubectl exec -n gitea deploy/gitea -- \
  gitea actions generate-runner-token | tail -n 1 | tr -d '\r\n')"
kubectl create secret generic act-runner-token \
  -n gitea-actions \
  --from-literal=token="$TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart -n gitea-actions deploy/act-runner
kubectl logs -n gitea-actions deploy/act-runner -c runner --tail=50
```

Expected runner log:

```text
runner: cluster-runner-1 ... declare successfully
```

For radar-ng, the recovery images are pinned in
`my-apps/development/radar-ng/`. If the registry is empty and the runner is not
usable yet, manually refill the exact pinned tags from local checkouts:

```bash
cd ~/programming/radar-ng/backend
VERSION=v1.1.4 ./scripts/build-push.sh tile-server
VERSION=v1.1.1 ./scripts/build-push.sh basemap open-meteo-worker
VERSION=v1.1.7 ./scripts/build-push.sh temporal-worker

cd ~/programming/talos-argocd-proxmox
./scripts/build-push-custom-apps.sh basemap-bootstrap
kubectl -n radar-ng delete job basemap-bootstrap
kubectl -n radar-ng rollout restart deploy/tile-server deploy/basemap deploy/open-meteo
kubectl -n radar-ng delete pod -l app=radar-ng-worker
```

On this single-worker cluster, `Insufficient cpu` during recovery usually means
requested CPU is saturated, not that the Proxmox host is busy. Verify with:

```bash
kubectl describe node talos-singlenode-gpu-prod-gpu-workers-f7x5ct \
  | sed -n '/Allocated resources:/,/Events:/p'
kubectl top nodes
```

## Post-restore acceptance

State BOTH claims, with live numbers:

1. **Restore contract**: every backed-up PVC `Bound` via its kopiur `Restore`
   populator (none stuck `Pending`), and the first post-restore `Snapshot` for
   each source reaches `Succeeded`. Cross-check per namespace:
   `kubectl -n <ns> get pvc,restore,snapshot`.
2. **Exemption hygiene**: every intentionally backup-exempt PVC is still bound
   and still carries the fully-qualified
   `storage.vanillax.dev/backup-exempt-reason` annotation — non-zero isn't a
   restore failure but it masks real problems (history: two exempt PVCs once sat
   unnoticed because acceptance only quoted the protected counters). PostHog's
   ClickHouse/Kafka/Redis, standalone Redis, and `project-nomad/nomad-storage`
   are the expected exempt set (PostHog's `postgres-data` is protected — it
   carries the API keys/dashboards); CNPG is not in either count — it recovers
   via Barman/S3 (separate system).

---

## The restore canary

Point-in-time acceptance rots; the canary provides a safe, isolated place to
repeat the proof.

`my-apps/system/restore-canary/` re-runs the real DR path against a dedicated test
PVC: its `kopiur/restore-canary-data.yaml` stub carries the `SnapshotPolicy` +
`SnapshotSchedule` + `Restore`, and the PVC's `dataSourceRef` points at the `Restore`.
The `SnapshotSchedule` keeps a fresh snapshot and a weekly quick verification
checks repository blobs. Those automated checks do **not** prove a restore. To
drill the full path, write and hash a sentinel, force and wait for a successful
snapshot, delete only the canary PVC, and let Argo recreate it via its
`dataSourceRef` → `Restore` populator:

```
sentinel (old UID + sha256) → forced kopiur Snapshot
→ delete ONLY the canary PVC → Git/Argo recreate with dataSourceRef → Restore
→ kopiur populator restore → byte-identical verification
```

A manually executed passing drill proves the *entire* chain — Git render, kopiur CR wiring,
kopia round-trip, populator restore — with data integrity checked by hash,
never touching production PVCs. Results land as
`restore-canary.vanillax.dev/last-drill-*` annotations on the namespace.

Treat a missing or stale `last-drill-*` annotation as “restore not recently
proven,” even when snapshots and quick verification are green. Automating the
destructive PVC deletion is intentionally deferred until a kopiur-native,
namespace-contained drill helper has been reviewed.

What it does **not** prove: restores of backups older than its own, CNPG
recovery (separate system), or app-level data semantics — drill those
separately when they matter.

## Failure-mode catalog

Worked fixes for the things a hostile rebuild throws at you — stale CSI attachments,
read-only filesystems, wedged clone PVCs, finalizer-stuck resources — live in the
[common failure modes table](storage-architecture.md#common-failure-modes).
