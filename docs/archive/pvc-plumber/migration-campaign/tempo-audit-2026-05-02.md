> [!WARNING]
> Historical document.
> This file is preserved for context only and is not the current runbook.
> Start with: [pvc-plumber-start-here](../../../pvc-plumber-start-here.md) or [docs index](../../../index.md).

# Tempo audit — 2026-05-02

Holistic read-only review of the `talos-argocd-proxmox` repo and live cluster, conducted via a `claude-tempo` ensemble of six parallel specialist agents. No file edits, no `kubectl` mutations.

## Methodology

| Phase | Specialist | Scope |
|---|---|---|
| 1 | conductor | Repo map (depth 4), cluster reachability probe |
| 2 | argocd-review | Self-management, AppProjects, ApplicationSets, sync waves, syncOptions, ignoreDifferences, ignoreApplicationDifferences, hooks |
| 3 | storage-dr-review | PVC backup/restore, pvc-plumber, VolSync/Kopia, CNPG/Barman, FAIL-CLOSED gate |
| 4 | kyverno-review | Policies (validate/mutate/generate), webhook exclusions, canonical defaults, HA, PolicyReports |
| 5 | temporal-review | temporal-worker-controller, temporal server, news-reader-temporal-worker, CNPG temporal DB |
| 6 | live-cluster-readonly | Read-only `kubectl get/describe/logs` across nodes, apps, PVCs, RS/RD, Kyverno, CNPG, events |
| 7 | docs-cleanup | Nested CLAUDE.md tree, `docs/`, `scripts/` |
| 8 | conductor | Synthesis |

Hard rules enforced: no `apply/delete/patch/edit/scale`, no `argocd app sync/refresh/delete`, no secret content emitted to logs.

---

## Active incident (in flight at audit time)

> **⚠ Worker `talos-prod-cluster-workers-smgrbs` died ~13:07 UTC on 2026-05-02.** This is in-flight, not an audit finding to schedule. It dominates the live-cluster section of this report and is the root cause of most current "non-Healthy" ArgoCD applications. See [the incident detail](#incident-detail) below.

---

## Findings — by severity

### Critical

#### C1. Bootstrap script will trigger a chart upgrade on first sync

| | |
|---|---|
| **Evidence** | `scripts/bootstrap-argocd.sh:100` → `--version 9.4.15` vs `infrastructure/controllers/argocd/kustomization.yaml:18` → `version: "9.5.9"` |
| **Why** | `helm install` lays down 9.4.15. As soon as `root.yaml` is applied, the self-managed argocd App syncs the kustomize-rendered 9.5.9 — turning bootstrap into a chart upgrade. The argocd.yaml:30-36 inline comment documents this exact wedge from 2026-05-01 (Renovate PR #1259). Repros deterministically on every fresh cluster install. |
| **Fix** | Match `bootstrap-argocd.sh:100` to the kustomization, or have the script grep the version out of `kustomization.yaml` so they stay in lockstep. |

#### C2. Active incident — see [Incident detail](#incident-detail)

---

### High

#### H1. AppProjects are effectively cluster-admin

| | |
|---|---|
| **Evidence** | `infrastructure/controllers/argocd/apps/projects.yaml:18-60` — all three projects (`infrastructure`, `my-apps`, `monitoring`) carry identical `clusterResourceWhitelist: '*'/'*'` and `destinations: '*'`. |
| **Why** | A buggy/compromised `my-apps` Application can install ClusterRoles, CRDs, MutatingWebhookConfigurations, mutate `kube-system`. Project boundaries are nominal — provide zero blast-radius reduction. May be a deliberate homelab convenience choice, but no comment indicates that. |
| **Fix** | At minimum, restrict `my-apps` `destinations` to namespaces matching `my-apps-*` or an explicit allowlist; drop ClusterRole/ClusterRoleBinding/CRD/Webhook* from `my-apps` `clusterResourceWhitelist`. Or document the intentional choice. |

#### H2. Orphan namespace `kyverno-vpa-policies` with no Git source

| | |
|---|---|
| **Evidence** | `kubectl get ns kyverno-vpa-policies` → Active, created `2026-04-17T18:45:31Z`, contains zero resources, no ArgoCD tracking labels. `grep -rln 'kyverno-vpa\|kyverno_vpa'` returns no matches outside the vendored Helm chart. |
| **Why** | Meanwhile `infrastructure/controllers/kyverno/values.yaml:72-83,109-120` grants Kyverno cluster-wide `create/delete/update` on `VerticalPodAutoscaler` resources via `extraResources` — privilege granted, no policy in Git uses it. Either RBAC is leftover from a deleted experiment or a policy YAML was never committed. |
| **Fix** | Decide: remove the VPA `extraResources` blocks from `values.yaml` if no VPA generate-policies are planned, OR restore the missing policy YAML to Git and check it into kustomization. |

#### H3. 19 manual-trigger VolSync ReplicationSources last synced 3 days ago

| | |
|---|---|
| **Evidence** | `kubectl get replicationsource -A` — 19 of 27 last synced `2026-04-29T03:2x:xxZ` with `NEXT SYNC` blank (manual-trigger mode). Affected: home-assistant, n8n, paperless-ngx, karakeep, gitea, perplexica, project-zomboid, project-nomad. |
| **Why** | NULL `NEXT SYNC` is expected for manual-trigger; 3 days without a sync is not. Compounded by H4 (broken trigger script). RPO gap on critical apps is 3 days. |
| **Fix** | Convert critical manual-trigger sources to scheduled (e.g., daily) so backups don't depend on a working trigger script. Or fix `trigger-immediate-backups.sh`. |

#### H4. Two scripts are misleading-broken

| | |
|---|---|
| **Evidence (a)** | `scripts/build-push-custom-apps.sh:31-34` references `my-apps/development/news-reader/app/` and `my-apps/development/temporal-worker/`. Neither exists. `find . -name Dockerfile` returns ZERO matches anywhere in the repo. |
| **Evidence (b)** | `scripts/trigger-immediate-backups.sh:51-63` creates `longhorn.io/v1beta2 Backup` CRs and selects volumes by label `recurring-job.longhorn.io/<tier>=enabled`. Zero such labels exist in `infrastructure/` or `my-apps/`. The cluster moved to Kyverno → VolSync → Kopia → NFS per `docs/volsync-storage-recovery.md` (2026-05-02). Also references MinIO at `192.168.10.133:9002` — backup target is now NFS / RustFS S3, not MinIO. |
| **Why** | Operators reaching for either tool today get errors or silent zero-effect. Companion `docs/plans/2026-04-19-followup-notes.md:31-40` instructs the same wrong build-push paths. |
| **Fix** | (a) Restore Dockerfiles + `app/` subdirs in repo, OR delete the script and document where the build pipeline actually lives. (b) Delete OR rewrite to trigger VolSync `ReplicationSource` immediate runs (Kyverno-generated names follow `<pvc>-backup`). |

#### H5. `my-apps` AppSet exclude pattern doesn't match (resolved)

| | |
|---|---|
| **Evidence** | The old AppSet used `path: my-apps/home/project-nomad/*`, which never excluded the parent app directory matched by `path: my-apps/*/*`. |
| **Resolution** | `project-nomad` is now intentionally managed by `infrastructure/controllers/argocd/apps/appsets/my-apps-appset.yaml` as one bundled app at `my-apps/home/project-nomad`. The bad exclude was removed. |
| **Verify** | `kubectl get app my-apps-project-nomad -n argocd`; the app should exist and point to `my-apps/home/project-nomad`. |
| **Follow-up** | Do not add child `kustomization.yaml` files under `my-apps/home/project-nomad/*` unless you also change the generator strategy. |

---

### Medium

#### M1. `cnpg-barman-plugin-app` sync wave is ahead of the CNPG operator

| | |
|---|---|
| **Evidence** | `cnpg-barman-plugin-app.yaml` is sync-wave 3; the CNPG operator is in the database AppSet (wave 4, glob `infrastructure/database/*/*`). |
| **Why** | Plugin renders before the operator/CRDs exist on cold bootstrap. ArgoCD retries forever (`retry.limit: -1`), so it self-heals — but the wave doctrine is misleading. |
| **Fix** | Move the CNPG operator out of the database glob and run as a standalone wave-3 App, or move the plugin to wave 4 with retry-on-dependency. |

#### M2. Legacy `nfs:` block in 4 infra files

| | |
|---|---|
| **Evidence** | `pvc-plumber/deployment.yaml:107-110`; `volsync/kopia-maintenance-cronjob.yaml:157-160`; `kopia-ui/deployment.yaml:85`; `kyverno/policies/volsync-nfs-inject.yaml:30-33`. All mount `192.168.10.133:/mnt/BigTank/k8s/volsync-kopia-nfs`. |
| **Why** | CLAUDE.md says legacy `nfs:` block silently ignores `mountOptions`. No `nconnect=16`, `rsize=1048576`, `nfsvers=4.1` — likely capped at ~140 MB/s on a 10G fabric. Every Kopia mover Job (the workhorse of every backup) gets a non-tuned mount. |
| **Fix** | Convert to inline CSI volume (`csi.driver: nfs.csi.k8s.io`) with explicit `volumeAttributes` and `mountOptions`, or pre-create a static PV per consumer. |

#### M3. `immich-server` uses RollingUpdate on a RWO PVC

| | |
|---|---|
| **Evidence** | `my-apps/media/immich/deployment-server.yaml:11-12,110-111` — `strategy.type: RollingUpdate` with `library` (RWO Longhorn PVC). |
| **Why** | Direct CLAUDE.md violation. Currently `replicas: 1` so it self-heals after termination grace, but it's textbook Multi-Attach deadlock waiting for the next chart upgrade or HA scale-out attempt. |
| **Fix** | Change to `strategy.type: Recreate`. |

#### M4. `n8n` chart `existingClaim: data` against backup-labeled RWO PVC

| | |
|---|---|
| **Evidence** | `my-apps/home/n8n/values.yaml:18` — `existingClaim: data`. n8n is upstream Helm chart whose default strategy is `RollingUpdate`. No `strategy.type: Recreate` override in our values. |
| **Why** | Same Multi-Attach risk on every chart upgrade. |
| **Fix** | Add the chart-equivalent strategy override (verify the n8n chart's key path). Confirm with `kubectl get deploy -n n8n n8n -o jsonpath='{.spec.strategy}'`. |

#### M5. Temporal CNPG recovery overlay is a DR landmine

| | |
|---|---|
| **Evidence** | `infrastructure/database/cloudnative-pg/temporal/overlays/recovery/bootstrap-patch.yaml:9-10` — `recoveryTarget.targetTime: "2026-04-16T23:59:59Z"`. |
| **Why** | After the 2026-04-19 RustFS baseline reset, that timestamp predates any extant WAL in the current `-v1` lineage. CLAUDE.md explicitly warns this FATALs Postgres recovery. Other CNPG DBs may have the same pattern — audit all `overlays/recovery/bootstrap-patch.yaml` files under `infrastructure/database/cloudnative-pg/`. |
| **Fix** | Either omit `recoveryTarget` (recovers to latest available WAL), or update to a verified-archived timestamp. Combine with bumping base `serverName` to `-v(N+1)` and recovery `externalClusters.serverName` to `-vN` per the database CLAUDE.md DR runbook. |

#### M6. Temporal server image and chart unmanaged by Renovate

| | |
|---|---|
| **Evidence** | `my-apps/development/temporal/values.yaml:9-12` — `temporalio/server:1.30.4`, no `# renovate:` datasource. `kustomization.yaml:24-26` — chart `temporal 1.1.1`, no datasource hint. `namespace-init-job.yaml:36` mounts `temporalio/admin-tools:1.30.4`, also unpinned. |
| **Why** | values.yaml comment literally says "Bump this line whenever a relevant fix lands" — manual tracking. CVE/fix delivery depends on someone remembering. |
| **Fix** | Add `# renovate: datasource=docker depName=temporalio/server` and `# renovate: datasource=helm depName=temporal registryUrl=https://go.temporal.io/helm-charts` comments. Add packageRule constraining temporal chart to patch/minor only. |

#### M7. Temporal worker controller `replicas` override is dead-letter

| | |
|---|---|
| **Evidence** | `infrastructure/controllers/temporal-worker-controller/values.yaml:27-28` sets `controller.replicaCount: 1`. Upstream chart uses top-level `replicas` (`charts/.../values.yaml:58`). Live: `kubectl get pods -n temporal-worker-controller` shows 2 manager pods. |
| **Why** | The "single-replica is fine for homelab" intent in the comment isn't applied. Override is silently ignored. |
| **Fix** | Replace with top-level `replicas: 1`, or accept the chart default and update the comment. |

#### M8. `longhorn-pvc-backup-audit.yaml` opts into `background: true`

| | |
|---|---|
| **Evidence** | `infrastructure/controllers/kyverno/policies/longhorn-pvc-backup-audit.yaml:16-23`. |
| **Why** | It's validate-only, so the strict CLAUDE.md prohibition (which targets generate policies for API-server overload reasons) doesn't fully apply. But it's the only policy in the tree opting in — contradicts project-wide canonical form. |
| **Fix** | Drop `background: true` and rely on a one-shot scan, or add a comment to CLAUDE.md carving out an explicit "audit-only" exception. |

#### M9. `volsync-nfs-inject.yaml` missing canonical defaults

| | |
|---|---|
| **Evidence** | `infrastructure/controllers/kyverno/policies/volsync-nfs-inject.yaml:13-14` — no spec-level `mutateExistingOnPolicyUpdate`, `background`, `emitWarning`, `validationFailureAction`. |
| **Why** | Kyverno's webhook will inject defaults; ArgoCD detects the diff → perpetual OutOfSync risk per the CLAUDE.md kyverno warning. |
| **Fix** | Add the canonical 4-key spec stanza explicitly: `mutateExistingOnPolicyUpdate: false`, `background: false`, `emitWarning: false`, `validationFailureAction: Audit`. |

#### M10. `docs/argocd.md` standalone-app table missing 3 apps

| | |
|---|---|
| **Evidence** | `docs/argocd.md:47-58` lists 10 standalone apps. Current standalones also include `keda-app` (Wave 4), `temporal-worker-controller-app` (Wave 4), `cnpg-barman-plugin-app` (Wave 3). |
| **Fix** | Add three rows; reference each app file's "why standalone" comment. |

#### M11. `docs/network-topology.md` worker IPs may be stale

| | |
|---|---|
| **Evidence** | Doc lists workers at `.164/.219/.159`. `infrastructure/networking/cilium/policies/` whitelist references `.14, .46, .133, .174, .32/27`. |
| **Fix** | Verify against current Omni / `kubectl get nodes -o wide`, then update. |

#### M12. `docs/plans/2026-03-16-project-nomad-k8s-openai.md` shipped but not archived

| | |
|---|---|
| **Evidence** | All 9+ services listed in the plan exist under `my-apps/home/project-nomad/`. |
| **Fix** | Move to `docs/plans/done/` or add a `Status: SHIPPED YYYY-MM-DD` header. Same audit needed for `docs/plans/2026-04-19-followup-notes.md`. |

---

### Low (selected)

- **L1.** Repeated `ignoreDifferences` blocks across 6 AppSets/Apps for ExternalSecret/HTTPRoute/PVC — should be hoisted into argo-cd `values.yaml` `resource.customizations.ignoreDifferences`. Drift risk if upstream schemas change.
- **L2.** Three sync-wave annotations on PVC Plumber inner resources (Deployment wave 1, ES wave 0) contradict the wrapping App's wave 2 — cosmetic confusion only.
- **L3.** `infrastructure-appset` uses bare `{{path.basename}}` while other AppSets prefix; collision footgun if anyone moves a standalone app into the AppSet path.
- **L4.** `kyverno-app.yaml` has `selfHeal: true` — `scripts/emergency-webhook-cleanup.sh` could race against ArgoCD self-heal during recovery. Test the recovery flow against current self-heal config.
- **L5.** `scripts/validate-argocd-apps.sh:24` glob lists `kyverno-app.yaml` twice (matches `*-app.yaml` AND the explicit name). Inflates standalone count, doesn't break anything.
- **L6.** No `docs/README.md` index. `docs/superpowers/plans/` and `docs/research/storage/review/` (18 files, ~280 KB) are uncatalogued.
- **L7.** Missing docs for: self-hosted Renovate CronJob, Temporal stack architecture, Open WebUI function-loader pattern.
- **L8.** Per-chart Renovate pin not implemented for `kyverno`/`kube-prometheus-stack`/`longhorn`/`cilium`. Global rule blocks major auto-merge for all helm-values, so spirit is satisfied — but no explicit `packageRules` belt-and-suspenders.
- **L9.** `radar-ng-worker-v1-0-5-bd49`: `ImagePullBackOff` — unrelated to node failure, bad tag.
- **L10.** `radar-ng-open-meteo-worker`: `OCI runtime create failed: exec: "./openmeteo-api": stat ./openmeteo-api: no such file or directory` — entrypoint binary missing from image.
- **L11.** Plumber readiness probe is slow: `initialDelaySeconds: 60`, `periodSeconds: 30`. Worst-case a pod stays Ready ~75 s after Kopia hangs.
- **L12.** Argocd self-managed App has `prune: false` but no inline comment explaining why (intentional self-protection); a future contributor may "fix" it.
- **L13.** CNPG `enableSuperuserAccess: true` on `temporal` cluster (`base/cluster.yaml:31`); CNPG best practice is `false` post-bootstrap.

---

## Healthy patterns to preserve

These look unusual but are deliberately load-bearing — captured so future audits/refactors don't break them.

1. **PVC Plumber 3-call admission gate** — 1 mutate + 2 validate `/exists` calls with explicit `apiCall.default` for fail-closed behavior; singleflight de-dup in plumber 1.7.0.
2. **`skip-restore` escape hatch** — required reason annotation + 24h Prometheus watchdog alert.
3. **Database AppSet `selfHeal: false` + `ignoreApplicationDifferences`** — both pieces required for documented DR runbook to work; selfHeal:true would strip manual annotations.
4. **CNPG overlay-pattern DR** — `base/` + `overlays/{initdb,recovery}/` keeps `bootstrap.initdb` and `bootstrap.recovery` mutually exclusive in the rendered manifest.
5. **argocd self-managed App bounded retry** — `retry.limit: 10` (not -1) with incident-grounded comment from 2026-05-01 wedge.
6. **Kyverno standalone (not in AppSet)** — wave 3, intentional. Webhooks must register before app PVCs deploy at wave 6; AppSets are "healthy" immediately on creation, which would race the registration.
7. **8-namespace Kyverno webhook exclusions** — `longhorn-system`, `argocd`, `volsync-system`, `cilium-secrets`, `kube-system`, etc. Removing any can cause full cluster deadlock if Kyverno crashes.
8. **Kyverno HA + canonical generate-policy form** — 3 admission replicas, PDB(`minAvailable: 2`), topology spread. The `volsync-pvc-backup-restore` policy is textbook canonical: `background: false`, `synchronize: false`, `mutateExistingOnPolicyUpdate: false`, `emitWarning: false`, `skipBackgroundRequests: true` all explicit.
9. **Server-side-diff + ServerSideApply everywhere** — avoids silent-no-op ConfigMap drift class of bug.
10. **Longhorn node-failure pinning** — `node-down-pod-deletion-policy=delete-both`, `node-drain-policy=block-if-contains-last-replica`, `replicaAutoBalance=best-effort`, default replica count 2. As a Setting CRD (not just chart values) so longhorn-manager won't revert.
11. **`apps/kustomization.yaml` enumeration is complete** — every YAML in the directory is listed; no silent misses.
12. **All non-excluded user Jobs carry `argocd.argoproj.io/hook` + `hook-delete-policy`** annotations.
13. **No `Replace=true,Force=true`** in any user-controlled manifests.
14. **Custom Lua health checks** in argocd `values.yaml:55-107` for Application/ClusterPolicy/RS/RD — sync waves actually gate on real readiness.

---

## Cross-cutting threads

1. **Talos `1.13.0-rc.0` is still on 3 nodes** including the dead one. Last commit `8f078eb9` bumped templates to GA; cluster nodes were never drained-and-rebuilt onto GA. Suggest a rolling reimage.
2. **Renovate coverage gaps cluster around hand-rolled deployments** (Temporal server, custom apps without Dockerfiles in repo). Either adopt Renovate hints uniformly or formalize the manual-bump list in CLAUDE.md.
3. **Several "clearly intentional but undocumented" patterns** — `prune: false` on argo self-app, `background: true` on audit policy, `RollingUpdate` on n8n/immich. Each needs a one-line "why" comment to survive future audits (human or LLM).
4. **Doc/code drift is small but real** — `argocd.md` missing apps, `network-topology.md` stale IPs, plan files not archived. Periodic `validate-argocd-apps.sh`-style check for docs would help.

---

## Incident detail

> **Status at audit time: in flight. Not an audit finding to schedule — the cluster is hurting now.**

### Root cause

Worker `talos-prod-cluster-workers-smgrbs` died around 13:07 UTC 2026-05-02. Kubelet stopped posting heartbeat; Talos auto-cordoned with annotation `talos.dev/cordoned: true`. Node was running Talos `v1.13.0-rc.0` (release candidate) — the 3 control planes and 2 other workers are on `v1.13.0` GA. Three nodes total still on rc.0 including this one, the GPU worker, and one other worker. The most recent commit before the audit (`8f078eb9`) bumped example/template configs to GA without cycling the actual nodes.

### Cascade

- 4 Longhorn volumes **faulted**: `paperless-ngx/data`, `paperless-ngx/media`, `prometheus-stack/grafana`, `loki-stack/loki-backend-0`.
- Pods in CrashLoop with hard I/O errors:
  - grafana — `mkdir: can't create directory '/var/lib/grafana/plugins': I/O error`
  - clickhouse — `mkdir: cannot create directory '/var/lib/clickhouse/tmp/': Input/output error`
- ArgoCD — `my-apps-posthog` is `OutOfSync + Missing`; ~10 apps `Progressing` waiting on volumes.
- CNPG `paperless-database` reports `HTTP communication issue` (Barman→S3 backups still completing — `paperless-daily-backup` ran 6m41s before audit).
- ~20 Longhorn volumes degraded — replicas on dead node need eviction → rebuild on survivors.
- 9 pods Pending/CrashLoop including `cilium-envoy-kdgkx`, `node-exporter`, `otel-agent-collector`.

### Independent failures (not caused by node death)

- `radar-ng-worker-v1-0-5-bd49` — `ImagePullBackOff` (bad image tag).
- `radar-ng-open-meteo-worker` — `OCI runtime create failed: exec: ./openmeteo-api: stat ./openmeteo-api: no such file or directory` (binary missing from image).
- PVC Plumber mid-rollout — uncommitted `infrastructure/controllers/pvc-plumber/deployment.yaml` (3 pods, 2 ReplicaSets, 3 ArgoCD syncs in last 20 min).

### Suggested triage order

1. Bring `smgrbs` back (Proxmox console / Talos reset) OR formally evict it from Longhorn.
2. Let Longhorn rebuild faulted volumes on surviving nodes.
3. Confirm clickhouse/grafana recover after volume reattach.
4. Fix radar-ng (image tag + entrypoint — independent of node).
5. Finish PVC Plumber rollout (commit `deployment.yaml`).
6. Reimage remaining `1.13.0-rc.0` nodes onto GA.

---

## Mink notes

This audit also persisted findings to the user's mink wiki vault at `~/.mink/wiki/`. Index note:
[`projects/talos-argocd-proxmox/audit-summary-2026-05-02-claude-tempo-holistic-read-only-review.md`](../../../.mink/wiki/projects/talos-argocd-proxmox/audit-summary-2026-05-02-claude-tempo-holistic-read-only-review.md)

13 notes total: 1 audit-summary index, 1 incident report, 5 architectural/gotcha references, 6 follow-up work items.

---

*Generated by `claude-tempo` ensemble — conductor + 6 parallel specialists, read-only. No files were edited and no cluster mutations were performed during this audit.*
