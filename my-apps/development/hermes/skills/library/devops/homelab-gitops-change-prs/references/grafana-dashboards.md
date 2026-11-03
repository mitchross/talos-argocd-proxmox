# Grafana dashboards as code (status / "what's broken now" boards)

The user wants live state, not daily report text. Alertmanager's UI is too ugly to use, and a custom status site would duplicate what Grafana already does. So for "I only care what's happening now", build a Grafana dashboard in the repo, in the Start Here folder. Don't propose a new site, Karma, or a Temporal pipeline.

## Procedure
0. Before saying a board doesn't exist, `git grep -l <metric_prefix> origin/main -- 'monitoring/**/dashboards/**/*.json'` (and list `dashboards/*/`). Board ConfigMaps are named after the board (`ai-gateway-analytics-dashboard`), not the metric source, so grepping `kubectl get cm -l grafana_dashboard` output for the source name misses them and the user has to correct you.
1. Read `monitoring/metrics/prometheus-stack/dashboards/README.md`. Dashboards are JSON files, one folder per Grafana folder, each listed in that folder's `kustomization.yaml` configMapGenerator. Use fixed datasource uid `prometheus`, `"id": null`, `"editable": false`, and a stable readable `uid`.
2. Pick metrics and prove each exists live first (`/api/v1/query` on in-cluster Prometheus). Known-good sources:
   - firing alerts: `ALERTS{alertstate="firing",alertname!~"Watchdog|InfoInhibitor"}`; for "firing since" use `(ALERTS_FOR_STATE{...} * 1000) and ignoring(alertstate) ALERTS{alertstate="firing",...}` with unit `dateTimeFromNow`
   - Argo: `argocd_app_info{health_status!="Healthy"} or argocd_app_info{sync_status!="Synced"}` (label `name`)
   - nodes: `kube_node_status_condition{condition="Ready",status="true"} == 0`
   - stuck pods: `kube_pod_status_phase{phase=~"Pending|Failed|Unknown"} == 1`
   - restarts: `sum by (namespace,pod)(increase(kube_pod_container_status_restarts_total[1h])) > 0.5`
   - kopiur: `kopiur_snapshot_consecutive_failures > 0` or `(time() - kopiur_policy_last_backup_success_timestamp_seconds) > 129600` (labels `exported_namespace`, `policy`)
   - Longhorn: `longhorn_volume_robustness` has one series per `state` with value 0/1, reported by several managers, so use `max by (pvc_namespace,pvc,state)(longhorn_volume_robustness{state=~"degraded|faulted"}) == 1`
3. Generate the JSON with a script, not by hand: `templates/status-dashboard.py` (edit the panel list, run it with the output path). Layout: a row of stat tiles (`count(...) or vector(0)`, green at 0 and red at 1 or more, `colorMode: background`), then one instant `format: table` per tile. Put `filterFieldsByName` FIRST in each table, then `organize` to rename and order, because label sets vary per series and noise columns otherwise leak in. Set `noValue: "All clear"` on tables. Refresh 1m, timepicker hidden.
4. Before the PR, run every panel `expr` through `/api/v1/query` and print status and count per panel. `kubectl kustomize <folder>` must render the new ConfigMap. Add a line to the README folder table.
5. Grafana's API needs a login the Hermes pod doesn't have, so the layout can't be previewed. Say so in the PR body and ask the user to check `/d/<uid>` after merge.

## Pitfalls
- Don't change the Grafana home page (`performance-cockpit.json`, set in `grafana.ini`) without asking. Add new boards next to it.
- A status board full of stale red trains the user to ignore it. Pair a new board with clearing the noise (next section), or offer to do that next.
- Grafana admin login comes from the 1Password `grafana` item via ExternalSecret `grafana-admin-credentials`, but `GF_SECURITY_ADMIN_PASSWORD` applies only on first run; Grafana's DB is on a PVC. To change it live: change it in Grafana (Profile > Change password), then set the same value in 1Password. Changing 1Password alone does nothing until a fresh volume.

## Usage boards from an app's own records
When an app keeps usage only in its own DB on an RWO volume (Hermes `state.db`), the reader must be a sidecar in that pod: a stdlib script under the app's `scripts/` (configMapGenerator), same image, same uid, read-only open (`file:...?mode=ro`), cached ~30 s, a metrics port on the Service and an app-owned ServiceMonitor; VPA entry `mode: "Off"`; no readiness probe. Expose running totals as `_total` counters plus an `<app>_exporter_up` gauge, and make the up gauge the first tile so a schema change after an app upgrade shows red. Generate the board JSON with a throwaway script and parse every expr against live Prometheus (substitute `$__range`/`$__interval`/vars) even though results are empty before deploy. Board queries use `increase(...[$__range])`; history before deploy reads 0. `increase()` drops a new label set's first sample, so a model with one call on a new surface never shows. Fix it in the exporter, not in PromQL: serve a label set first seen after startup as 0 for 2 scrapes plus the cache (the Hermes `usage-exporter` holds it for 180 s), and treat the first read as baseline. A PromQL `x - (x offset $__range or x*0)` rewrite counts the whole pre-deploy history as new, so don't use it. Hermes reports cost $0 for LiteLLM models (no price), and surface `local` means the CLI session source, not a local model. The PR restarts the pod; say so.

## Clearing alert noise
For each firing alert, decide: real fault (fix it), or a rule that misfires (fix the rule in Git). Then:
1. Pull firing alerts from Alertmanager (`:9093/api/v2/alerts`), skip Watchdog/InfoInhibitor.
2. For a suspect rule, find gaps over 14 days: `query_range` on the alert expr, group consecutive samples into runs, and line them up with pod restarts (`kube_pod_start_time`).
3. Before the PR, run the NEW expr over the same 14 days and state in the body which past windows it still catches and which it drops. A fix that hides a real outage is worse than the noise.

Known rule fixes:
- Stock `KubeJobFailed` fires for every failed Job a CronJob keeps in history, even after later successes. Disable it under `defaultRules.disabled` and alert on the latest run instead: `((kube_cronjob_status_last_schedule_time > kube_cronjob_status_last_successful_time) or (kube_cronjob_status_last_schedule_time unless on (namespace, cronjob) kube_cronjob_status_last_successful_time)) unless on (namespace, cronjob) (kube_cronjob_status_active > 0)`, plus `kube_job_failed > 0 unless on (namespace, job_name) kube_job_owner{owner_kind="CronJob"}` for standalone Jobs.
- `absent(<gauge>)` on a gauge emitted on a long timer fires after every restart until the first tick. Look up the emit interval in upstream source, then use `absent_over_time(<gauge>[<interval + margin>])` (Temporal `dlq_message_count`: emitted every 3h, so `[4h]`).
- Failed pods with reason "Terminated"/"imminent node shutdown" come from a node reboot, not a broken workload; check the time against node events before blaming pod-cleanup.
- One-off Jobs you create for debugging (manual migrate reruns) trip the standalone-Job alert when they fail. Set `ttlSecondsAfterFinished`, and offer to delete your own failed debug Job once its logs are read.
