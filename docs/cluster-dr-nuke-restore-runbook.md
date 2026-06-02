# Cluster Nuke / Rebuild / Restore Runbook

> **DO NOT EXECUTE ANY STEP IN THIS RUNBOOK WITHOUT EXPLICITLY TYPING `GO NUKE
> CLUSTER` TO THE OPERATOR. Every section below is reference material for the
> day you actually do this — not a script to run today.**

This runbook validates the operator-free VolSync/Kopia DR design under a full
cluster loss. It is the final confidence test for the "explicit per-PVC inline
PVC + ReplicationSource + ReplicationDestination + cluster-shared Kopia repo
via ClusterExternalSecret + MutatingAdmissionPolicy backend gate" architecture.

The runbook is intentionally verbose. A DR you do once a year, in a panic, is
not the moment to discover that step 6 silently fails when step 4 was skipped.

---

## Bootstrap guardrails (learned in the 2026-06-01 full-nuke drill)

The App-of-Apps wave gate won't advance a wave until its apps are **Healthy**, so any
"early-wave app depends on a later-wave thing" becomes a hard deadlock that freezes the rebuild.
Hard rules (each one is a real bug this drill found and fixed):

- **No bootstrap-critical app may render `monitoring.coreos.com` resources in its core path.**
  `ServiceMonitor`/`PodMonitor`/`PrometheusRule`/`Probe`/`AlertmanagerConfig`/dashboards must live in a
  **separate optional app that syncs AFTER kube-prometheus-stack (Wave 5)**. Those CRDs don't exist
  until Wave 5; an earlier app shipping them fails dry-run ("one or more synchronization tasks are not
  valid") and deadlocks the gate. *If deleting Prometheus breaks restore, the repo is wrong.* We
  deliberately do **NOT** install Prometheus Operator CRDs early. Fixed: pvc-plumber (Wave-2 core
  split), keda (`keda-observability` app at Wave 6 — commit `92c48f18`), opentelemetry-operator
  (`opentelemetry-operator-observability` app at Wave 6 — the operator is Wave 5, the *same* wave as
  kube-prometheus-stack, so its chart ServiceMonitor raced the CRD install; now split out).
- **CNPG `enablePodMonitor: true` is an ACCEPTED runtime soft-coupling, not an Argo blocker.** The CNPG
  clusters (gitea/immich/paperless/temporal, Wave 4) set `enablePodMonitor: true`. The PodMonitor is
  created by the **CNPG operator at reconcile time** (not rendered into Git, not part of an Argo sync),
  so on a fresh nuke the operator may log transient PodMonitor-create failures until kube-prometheus-stack
  installs the `monitoring.coreos.com` CRDs at Wave 5. This self-heals and never gates the Argo wave
  gate — leave it as-is. (Confirmed by the 2026-06-01 post-nuke observability audit.)
- **cert-manager is Wave 1**, not Wave 4 — anything mounting a cert-manager TLS secret (e.g.
  cnpg-barman-plugin, Wave 3) needs it early. (commit `d2471e71`)
- **No early-wave app may reference a not-yet-existing namespace** (e.g. a Role/RoleBinding hardcoded
  into a Wave-6 app's namespace). Removed from pvc-plumber Wave-2. (commit `01968bd4`)
- **pvc-plumber is manual-sync by design** (holds the cluster-wide volsync-writer CRB) — a human/agent
  must Sync it once after a nuke; the whole fleet is gated behind it until then.
- **`SkipDryRunOnMissingResource`** is only a temporary mid-rebuild escape hatch, or a permanent option
  on an **observability-only** app — never the long-term fix for a core app.
- **Restore depends on the external RustFS access key** (1Password item `rustfs`,
  `rustfs-workload-access-key`/`-secret-key`) being valid on the TrueNAS RustFS box; the cluster side
  pulls it via ClusterExternalSecret. Movers failing "Access Key Id … does not exist" = reconcile the
  key on RustFS, not a cluster/GitOps problem.

## Pre-Nuke Gates (block until ALL satisfied)

Run the validator first. If any gate fails, **do not nuke**.

| # | Gate | How to verify | Pass criteria |
|---|------|---------------|---------------|
| 1 | Static manifests render | `python3 hack/validate-volsync-wiring.py --exclude monitoring/prometheus-stack --exclude infrastructure/database/cnpg-barman-plugin --exclude infrastructure/storage/longhorn` | `wiring_failures: []`, `render_failures: {}`, and no unexpected inactive VolSync source docs |
| 2 | All backed-up PVCs have a working RS in the shared repo | `bash hack/volsync-status.sh` | every critical row shows `Successful` lastSyncTime within last 24h and `REPO_SECRET=volsync-kopia-repository` |
| 3 | No Argo app is `OutOfSync` for an app with backed-up PVCs | `kubectl get application -n argocd \| grep OutOfSync` | only OutOfSync apps are documented exceptions |
| 4 | kopia-maintenance Job has run successfully in the last 12h | `kubectl get jobs -n volsync-system \| grep kopia-maintenance` | most recent Complete < 12h; it must not mount the deleted `pvc-plumber-kopia` Secret |
| 5 | RustFS backup target reachable from outside the cluster | `nc -zw5 192.168.10.133 30292` from your laptop | port open |
| 6 | RustFS data survives the nuke | RustFS runs on TrueNAS (`192.168.10.133`), not in the cluster — **confirm visually** before nuking | bucket `volsync-kopia` lives outside cluster |
| 7 | 1Password vault `homelab-prod` has `rustfs` item with `kopia_password`, `rustfs-workload-access-key`, `rustfs-workload-secret-key` | 1Password UI | all three fields populated |
| 8 | 1Password Connect token + credentials saved OFF-CLUSTER | 1Password app, password manager | recoverable without the cluster |
| 9 | Talos + Omni provisioning files saved off-cluster | `omni/`, control plane bootstrap | secrets files (talosconfig, kubeconfig) backed up |
| 10 | Repo target revision recorded | `git rev-parse HEAD`, write it to your phone notes | the SHA you'll rebuild from |
| 11 | Cloudflare tunnel credentials saved off-cluster | Cloudflare dashboard | tunnel can be re-established |
| 12 | DNS records noted | `firewalla-dns-config.txt` is current | known A/AAAA/CNAME state |
| 13 | List of currently-running non-backed-up PVCs accepted as expected losses | grep `backup-exempt: "true"` | operator acknowledges these are gone |
| 14 | Argo CD can converge every app with a backed-up PVC | `kubectl get application -n argocd` | no `ComparisonError` or `OutOfSync` caused by immutable PVC `dataSourceRef` server-side diff |
| 15 | One end-to-end **restore drill** completed against a currently-running app | see `## Non-Destructive Restore Drill` below | passes for one simple + one multi-PVC app |

If any gate fails, the nuke is **NO GO**. Fix and re-validate.

---

## Reference: What Survives The Nuke

- **Outside the cluster (survive):**
  - RustFS S3 (TrueNAS 192.168.10.133:30292) — Kopia repo `s3://volsync-kopia/cluster`
  - 1Password Connect vault (cloud)
  - Cloudflare tunnel config
  - Git repo (GitHub)
  - Proxmox host, ZFS pools, VM disk backups
  - Talos image + Omni config

- **Inside the cluster (lost):**
  - All Longhorn PVs (every app's working PVC)
  - All ConfigMaps not declared in Git
  - All Secrets not produced by ExternalSecret/ClusterExternalSecret
  - VolSync RS/RD status (rebuilt from Git on bootstrap)
  - All non-backed-up data on `nfs-comfyui-10g` / `nfs-llama-cpp-10g` PVCs only survives if the NFS share is on TrueNAS, not on a worker node

---

## Nuke Steps (DESTRUCTIVE — only after `GO NUKE CLUSTER`)

Pick one of the two paths. Path A is faster but trusts Omni; Path B is from-scratch.

### Path A — Omni cluster destroy + recreate

```bash
# 1. Confirm the cluster you're about to destroy
omnictl get cluster talos-prod

# 2. Destroy
omnictl delete cluster talos-prod
# Omni tears down all member machines back to wipe state.

# 3. Recreate using the same template (config preserved in omni/)
omnictl cluster template sync --file omni/cluster-template/cluster-template.yaml
```

### Path B — wipe VMs, recreate Talos

```bash
# Stop and wipe every Talos VM in Proxmox.
# (List specific VM IDs here — do NOT script this; it's a one-time op.)
qm stop <vmid> ; qm destroy <vmid> --purge
# Reprovision via Omni from omni/cluster-template/cluster-template.yaml.
```

In either path you end up with a fresh K8s cluster, no workload state.

---

## Rebuild Steps

Order matters. Each layer's controllers must be ready before the next layer's
manifests apply, or you'll get cascading sync failures that look like real bugs.

### Layer 0 — Cluster bootstrap (manual)

1. Verify Talos cluster up: `talosctl health --nodes <node-ip>`
2. Verify K8s API reachable: `kubectl get nodes` (all `Ready`)
3. Verify K8s ≥ 1.34 so `admissionregistration.k8s.io/v1` (GA) is available:
   `kubectl api-resources --api-group=admissionregistration.k8s.io | grep mutatingadmissionpolicies`

### Layer 1 — Argo CD (manual bootstrap)

```bash
./scripts/bootstrap-argocd.sh
kubectl get pods -n argocd -w   # wait until all Running
kubectl apply -f infrastructure/controllers/argocd/root.yaml
```

Argo from this point applies everything else, by sync wave.

### Layer 2 — Wave 0 (Cilium, ArgoCD, 1P Connect, ESO, AppProjects)

Watch until ready:
```bash
kubectl get pods -n 1passwordconnect -w
kubectl get pods -n external-secrets -w
kubectl get clustersecretstore 1password   # must be Ready/Valid
```

### Layer 3 — Wave 1 (Longhorn, snapshot-controller, VolSync controller)

```bash
kubectl get pods -n longhorn-system    # wait Ready
kubectl get pods -n kube-system -l app=snapshot-controller  # wait Ready
kubectl get pods -n volsync-system     # volsync controller Ready
kubectl get crd | grep -E 'volsync.backube|snapshot.storage.k8s.io'
kubectl get volumesnapshotclass longhorn-snapclass
kubectl get storageclass longhorn
```

### Layer 4 — Wave 2 (MAP + ClusterExternalSecret for kopia repo)

This is the critical step. The MAP gates every mover Job behind RustFS
reachability, and the ClusterES produces the per-namespace
`volsync-kopia-repository` Secret in every namespace labeled
`volsync.backube/privileged-movers: "true"`.

```bash
# Verify MAP is registered
kubectl get mutatingadmissionpolicy volsync-mover-backend-availability
kubectl get mutatingadmissionpolicybinding volsync-mover-backend-availability

# Verify ClusterES registered + Ready
kubectl get clusterexternalsecret volsync-kopia-repository -o json | jq .status

# At this point no app namespaces exist yet, so no Secret is produced.
```

### Layer 5 — Wave 3 (CNPG plugin) — only needed before databases

`infrastructure/database/cnpg-barman-plugin`.

### Layer 6 — Wave 4 (Infrastructure + Databases AppSets)

`infrastructure-appset.yaml` and `database-appset.yaml` fire. Database Apps
do NOT auto-`selfHeal` so manual `skip-reconcile` annotations stick during
recovery. Watch:

```bash
kubectl get applications -n argocd -o custom-columns=\
NAME:.metadata.name,WAVE:.metadata.annotations.argocd\\.argoproj\\.io/sync-wave,SYNC:.status.sync.status,HEALTH:.status.health.status
```

### Layer 7 — Wave 5 (OTEL operator + monitoring AppSet)

Standard.

### Layer 8 — Wave 6 (`my-apps/*` discovered by my-apps AppSet)

This is where the restores happen.

Each app's `namespace.yaml` has label
`volsync.backube/privileged-movers: "true"` → ClusterES fires → Secret
`volsync-kopia-repository` materializes in the namespace.

Then the inline ReplicationDestination becomes valid (`spec.kopia.repository`
references that Secret).

Then the inline PVC is created with
`dataSourceRef: { apiGroup: volsync.backube, kind: ReplicationDestination,
name: <pvc>-dst }`.

VolSync's volume populator sees the dataSourceRef, calls the RD's mover Job
(which the MAP gates behind RustFS), the Job runs Kopia restore against
`s3://volsync-kopia/cluster` with the identity stored in
`spec.kopia.sourceIdentity`, snapshots the result into a temp PVC, then the
real app PVC is Bound from that snapshot.

Then the workload Deployment/StatefulSet starts and mounts the now-populated
PVC.

---

## Restore Observation

```bash
# Per namespace: watch the chain
NS=jellyfin
kubectl get externalsecret -n $NS                # ClusterES rendered the ExternalSecret
kubectl get secret -n $NS volsync-kopia-repository  # ESO populated the Secret
kubectl get replicationdestination -n $NS        # RD created
kubectl get jobs -n $NS -l app.kubernetes.io/created-by=volsync  # mover Job
kubectl logs -n $NS -l app.kubernetes.io/created-by=volsync -f   # restore progress
kubectl get pvc -n $NS                            # PVC binds when restore completes
kubectl get pods -n $NS                           # workload starts after PVC Bound
```

Watch all apps simultaneously:
```bash
bash hack/volsync-restore-watch.sh
```

---

## Post-Restore Checks

For every app, in order:

1. **PVC Bound and not Pending**
   `kubectl get pvc -A | grep -v Bound`
2. **Workload Ready**
   `kubectl get pods -A | grep -vE '(Running|Completed)'`
3. **Data spot-check**: for each app, manually open the UI or `kubectl exec`
   and verify a sentinel file or known content exists.
4. **ReplicationSource resumes scheduled backup**
   `kubectl get replicationsource -A`
   wait for the next schedule slot — verify `lastSyncTime` advances.
5. **MAP injects wait-for-rustfs in new mover Jobs**
   `kubectl get pods -A -l app.kubernetes.io/created-by=volsync \
     -o=jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}  init: {.spec.initContainers[*].name}{"\n"}{end}'`
   Every row should show `init: wait-for-rustfs`.
6. **kopia-maintenance CronJob succeeds**
   `kubectl get jobs -n volsync-system | grep kopia-maintenance`
7. **No failed VolSync Jobs leaked**
   `kubectl get jobs -A -l app.kubernetes.io/created-by=volsync \
     -o json | jq '.items[] | select(.status.failed > 0)'`
8. **No orphan dst-dest PVCs without an owning RD**
   `kubectl get pvc -A | grep volsync-.*-dst-dest`
   Cross-check each against a live RD.

---

## Failure Modes & Recovery

### "ExternalSecret missing in app namespace"

Cause: Namespace was created without the
`volsync.backube/privileged-movers: "true"` label, or the ClusterES selector
hasn't reconciled yet.

```bash
kubectl get ns $NS -o jsonpath='{.metadata.labels}{"\n"}'
kubectl label ns $NS volsync.backube/privileged-movers=true --overwrite
# Wait ~1 min for refreshInterval, or restart ESO controller.
```

### "Secret/volsync-kopia-repository missing"

Cause: ClusterES is producing the ExternalSecret but ESO can't reach 1P.

```bash
kubectl describe externalsecret -n $NS volsync-kopia-repository
kubectl logs -n 1passwordconnect -l app.kubernetes.io/name=connect
kubectl get clustersecretstore 1password
```

### "PVC stuck Pending"

Possible causes, in order of likelihood:

1. RD doesn't exist yet — check `kubectl get rd -n $NS`.
2. RD's mover Job is waiting on RustFS (MAP init container).
   `kubectl logs -n $NS <mover-pod> -c wait-for-rustfs --tail=20`
   Expect "waiting for rustfs s3" lines every 30s. If RustFS is reachable
   the message disappears and the mover proceeds.
3. snapshot-controller down.
4. Longhorn StorageClass down.
5. The ReplicationDestination's `sourceIdentity` doesn't match any snapshot
   in the Kopia repo for that user/host. Use the `Kopia repo verification`
   section below.

### "PVC Bound but app pod sees empty volume"

Cause: The PVC was created BEFORE the ReplicationDestination materialized,
so VolSync's volume populator did NOT inject snapshot data — the PVC bound
to an empty Longhorn volume.

`spec.dataSourceRef` only fires at PVC create time. Once a PVC is Bound, the
field is immutable. **Recovery: delete the PVC + workload, let GitOps
recreate them in the right order.** Do NOT manually copy data in; you'll
break the next backup's history.

### "RS/RD spec drift after sync"

Cause: ServerSideApply + a controller mutating the spec. Or `ignoreDifferences`
covering more than intended.

The repo-level `ignoreDifferences` on `PersistentVolumeClaim.spec.dataSourceRef`
is deliberate — once Bound, that field is immutable, so Argo must ignore it.
It is NOT applied to RS/RD; if you see RS/RD drift, the inline manifest is
authoritative.

```bash
kubectl diff -k my-apps/<category>/<app>/
```

### "Kopia repo says snapshot not found"

Verify the identity the RD is searching for:

```bash
kubectl get rd -n $NS <pvc>-dst -o jsonpath='{.spec.kopia.sourceIdentity}{"\n"}'
# Then connect to the kopia repo from a debug pod and list:
#   kopia snapshot list --user=<username> --host=<hostname>
# (Use a Job, not a kubectl run, to avoid PSA on default ns.)
```

If the identity doesn't match what was used at backup time, you're searching
the wrong namespace in the Kopia repo. Compare against
`Repo identity matrix` below.

### "RustFS unreachable on cold start, mover Jobs failing"

The MAP's init container TCP-probes RustFS for up to 1h. If RustFS is still
not back after 1h, the Job fails and Kubernetes Job backoff kicks in. Once
RustFS is reachable, the next retry succeeds.

Don't disable the MAP. Don't hand-edit Jobs. Restore RustFS and wait.

---

## Repo Identity Matrix

The inline ReplicationDestination tells VolSync which Kopia snapshot lineage
to restore from. The lineage is `(username, hostname, path)`. The inline
files in this repo use:

| RD field | Value |
|----------|-------|
| `username` | the PVC name (e.g. `config`, `library`) |
| `hostname` | the namespace name (e.g. `jellyfin`, `immich`) |
| `sourceIdentity.sourceName` | the PVC name |
| `sourceIdentity.sourceNamespace` | the namespace name |
| `sourceIdentity.sourcePVCName` | the PVC name |
| `repository` | `volsync-kopia-repository` (ClusterES-produced) → `s3://volsync-kopia/cluster` |

If the RS that wrote the snapshot used different `username`/`hostname`, the
RD won't find it. **All inline RS files in this repo use the SAME
`username`/`hostname` pair as their sibling RD**, so a restore from a backup
this repo took will find its snapshot.

### Pre-c401822a chart-era backups (legacy)

These wrote to a different Kopia repository entirely:
`s3://volsync-kopia/volsync-<pvc-name>` (one repo per PVC), not the shared
`/cluster` repo. They are reachable only by reusing the legacy per-PVC
secret, which has been deleted from Git. They are NOT recoverable through
the post-c401822a inline manifests without a one-time bridge backup. See
**Required Fixes** in the validation report.

---

## Rollback (if rebuild fails before all apps restored)

You can leave a partial cluster up indefinitely as long as RustFS is
reachable. Apps not yet restored simply have Pending PVCs. There is no
forced ordering on restore completion.

If a specific app's restore is wedged:
1. Annotate the Argo Application `argocd.argoproj.io/skip-reconcile: "true"`
2. Investigate without Argo fighting you
3. Remove the annotation when fixed

If the whole rebuild path is wedged: don't nuke again. Stop and triage. The
RustFS data is unchanged; the cluster can be poked indefinitely.

---

## What This Runbook DOES NOT Cover

- **CNPG database DR** — see `docs/domains/cnpg/disaster-recovery.md`. CNPG uses
  Barman to S3, not VolSync.
- **NFS-static-PV data** (immich photos, llama-cpp models) — these live on
  TrueNAS and survive the nuke; the PVs just need to be reapplied with
  matching CSI volumeHandles.
- **Cloudflare tunnel rebuild** — out of scope.
- **PostHog ClickHouse** — `clickhouse-data-*` is `backup-exempt: "true"`;
  data is regenerable from PostHog ingest.

---

## Validator Scripts Reference

| Script | Purpose | Read-only? |
|--------|---------|------------|
| `hack/validate-volsync-wiring.py` | render all manifests + validate PVC ↔ RD ↔ RS ↔ Secret wiring, emit `docs/volsync-dr-inventory.md` | yes |
| `hack/volsync-status.sh` | live RS/RD/PVC status table | yes |
| `hack/volsync-backup-all.sh` | trigger manual backup on every RS, wait for completion | writes RS specs |
| `hack/volsync-restore-watch.sh` | watch every RD + mover Job + PVC + workload during a rebuild | yes |

Run `hack/validate-volsync-wiring.py` before AND after the nuke; the inventory
should match (same 27 PVCs, same wiring, same `Successful` mover status).
