#!/usr/bin/env bash
# Restore the remaining legacy CNPG databases (paperless, temporal) on a
# freshly rebuilt cluster. Immich left CNPG for plain Postgres + kopiur —
# every immich backup lineage held an empty database, so there was nothing to
# recover. See docs/domains/cnpg/plain-postgres-migration.md.
#
# This script intentionally performs no deletes. The CNPG Applications and
# their consumers have automated sync disabled in their ApplicationSets, so a
# fresh cluster pauses at a safe boundary until this script advances it.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
ARGO_NAMESPACE="argocd"
CNPG_NAMESPACE="cloudnative-pg"
EXECUTE=false
APP_TIMEOUT_SECONDS="${CNPG_ARGO_TIMEOUT_SECONDS:-3600}"
CLUSTER_TIMEOUT_SECONDS="${CNPG_CLUSTER_TIMEOUT_SECONDS:-3600}"
BACKUP_TIMEOUT_SECONDS="${CNPG_BACKUP_TIMEOUT_SECONDS:-2400}"
RECOVERY_REVISION=""

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap-cnpg-recovery.sh [--execute]

Without --execute, validate and print the pinned recovery plan without
changing the cluster. With --execute, sync each database and consumer in this
order:

  database Application -> PostgreSQL lineage/data proof -> archive/backup
  proof -> consumer Application

This is for the prepared 2026-07-31 fresh-cluster recovery only. It never
deletes an existing Cluster or PVC and fails if existing state has the wrong
bootstrap lineage.
EOF
}

case "${1:-}" in
  "") ;;
  --execute) EXECUTE=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

for command_name in git kubectl kustomize jq; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $command_name" >&2
    exit 1
  fi
done

log() {
  printf '\n==> %s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

deadline_after() {
  echo $(( $(date +%s) + $1 ))
}

wait_for_application() {
  app_name="$1"
  deadline="$(deadline_after "$APP_TIMEOUT_SECONDS")"
  while ! kubectl -n "$ARGO_NAMESPACE" get application "$app_name" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      die "timed out waiting for Application/$app_name"
    fi
    sleep 10
  done
}

wait_for_application_idle() {
  app_name="$1"
  deadline="$(deadline_after "$APP_TIMEOUT_SECONDS")"
  while [ "$(kubectl -n "$ARGO_NAMESPACE" get application "$app_name" -o jsonpath='{.status.operationState.phase}' 2>/dev/null || true)" = "Running" ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      die "timed out waiting for the existing $app_name sync operation"
    fi
    sleep 10
  done
}

assert_manual_application() {
  app_name="$1"
  expected_path="$2"
  wait_for_application "$app_name"

  app_json="$(kubectl -n "$ARGO_NAMESPACE" get application "$app_name" -o json)"
  actual_path="$(printf '%s' "$app_json" | jq -r '.spec.source.path')"
  target_revision="$(printf '%s' "$app_json" | jq -r '.spec.source.targetRevision')"
  [ "$actual_path" = "$expected_path" ] || \
    die "$app_name targets $actual_path, expected $expected_path"
  [ "$target_revision" = "main" ] || \
    die "$app_name tracks $target_revision, expected main"
  printf '%s' "$app_json" | jq -e '.spec.syncPolicy.automated.enabled == false' >/dev/null || \
    die "$app_name still has automated sync enabled; wait for the ApplicationSet update"
}

hard_refresh_application() {
  app_name="$1"
  previous_reconciled="$(kubectl -n "$ARGO_NAMESPACE" get application "$app_name" -o jsonpath='{.status.reconciledAt}' 2>/dev/null || true)"
  kubectl -n "$ARGO_NAMESPACE" annotate application "$app_name" \
    argocd.argoproj.io/refresh=hard --overwrite >/dev/null

  deadline="$(deadline_after "$APP_TIMEOUT_SECONDS")"
  while true; do
    app_json="$(kubectl -n "$ARGO_NAMESPACE" get application "$app_name" -o json)"
    refresh_annotation="$(printf '%s' "$app_json" | jq -r '.metadata.annotations["argocd.argoproj.io/refresh"] // ""')"
    reconciled="$(printf '%s' "$app_json" | jq -r '.status.reconciledAt // ""')"
    if [ -z "$refresh_annotation" ] && [ -n "$reconciled" ] && [ "$reconciled" != "$previous_reconciled" ]; then
      echo "    $app_name hard refresh completed at $reconciled"
      return 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      die "timed out waiting for $app_name hard refresh"
    fi
    sleep 5
  done
}

sync_application() {
  app_name="$1"
  wait_for_application_idle "$app_name"
  hard_refresh_application "$app_name"
  previous_started="$(kubectl -n "$ARGO_NAMESPACE" get application "$app_name" -o jsonpath='{.status.operationState.startedAt}' 2>/dev/null || true)"

  operation_patch="$(jq -nc --arg revision "$RECOVERY_REVISION" \
    '{operation:{initiatedBy:{username:"bootstrap-cnpg-recovery"},sync:{revision:$revision,prune:true}}}')"
  kubectl -n "$ARGO_NAMESPACE" patch application "$app_name" --type merge \
    -p "$operation_patch" \
    >/dev/null

  deadline="$(deadline_after "$APP_TIMEOUT_SECONDS")"
  while true; do
    operation_json="$(kubectl -n "$ARGO_NAMESPACE" get application "$app_name" -o json)"
    started="$(printf '%s' "$operation_json" | jq -r '.status.operationState.startedAt // ""')"
    phase="$(printf '%s' "$operation_json" | jq -r '.status.operationState.phase // ""')"
    message="$(printf '%s' "$operation_json" | jq -r '.status.operationState.message // ""')"

    if [ -n "$started" ] && [ "$started" != "$previous_started" ]; then
      case "$phase" in
        Succeeded)
          echo "    $app_name sync succeeded"
          return 0
          ;;
        Failed|Error)
          die "$app_name sync $phase: $message"
          ;;
      esac
    fi

    if [ "$(date +%s)" -ge "$deadline" ]; then
      die "timed out waiting for $app_name sync; last phase=$phase message=$message"
    fi
    sleep 10
  done
}

wait_for_cluster_condition() {
  cluster_name="$1"
  condition_name="$2"
  timeout_seconds="$3"
  deadline="$(deadline_after "$timeout_seconds")"
  while true; do
    if kubectl -n "$CNPG_NAMESPACE" get cluster "$cluster_name" -o json 2>/dev/null | \
      jq -e --arg condition "$condition_name" \
        '.status.conditions[]? | select(.type == $condition and .status == "True")' >/dev/null; then
      echo "    Cluster/$cluster_name condition $condition_name=True"
      return 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      kubectl -n "$CNPG_NAMESPACE" get cluster "$cluster_name" -o wide 2>/dev/null || true
      die "timed out waiting for Cluster/$cluster_name condition $condition_name=True"
    fi
    sleep 15
  done
}

wait_for_backup() {
  backup_name="$1"
  deadline="$(deadline_after "$BACKUP_TIMEOUT_SECONDS")"
  while true; do
    backup_json="$(kubectl -n "$CNPG_NAMESPACE" get backup "$backup_name" -o json 2>/dev/null || true)"
    phase="$(printf '%s' "$backup_json" | jq -r '.status.phase // ""' 2>/dev/null || true)"
    case "$phase" in
      completed)
        backup_id="$(printf '%s' "$backup_json" | jq -r '.status.backupId // "unknown"')"
        echo "    Backup/$backup_name completed (backupID=$backup_id)"
        return 0
        ;;
      failed|error)
        message="$(printf '%s' "$backup_json" | jq -r '.status.error // .status.message // "no status message"')"
        die "Backup/$backup_name $phase: $message"
        ;;
    esac
    if [ "$(date +%s)" -ge "$deadline" ]; then
      die "timed out waiting for Backup/$backup_name (phase=${phase:-not-created})"
    fi
    sleep 15
  done
}

render_resources_json() {
  db_name="$1"
  kustomize build --enable-helm \
    "$ROOT_DIR/infrastructure/database/cloudnative-pg/$db_name" | \
    kubectl create --dry-run=client --validate=false -f - -o json | \
    jq -s '.'
}

assert_recovery_render() {
  db_name="$1"
  expected_read_lineage="$2"
  expected_backup_id="$3"
  expected_write_lineage="$4"

  resources_json="$(render_resources_json "$db_name")"
  cluster_json="$(printf '%s' "$resources_json" | jq '[.[] | select(.apiVersion == "postgresql.cnpg.io/v1" and .kind == "Cluster")][0]')"
  cluster_name="$(printf '%s' "$cluster_json" | jq -r '.metadata.name')"
  recovery_source="$(printf '%s' "$cluster_json" | jq -r '.spec.bootstrap.recovery.source // ""')"
  backup_id="$(printf '%s' "$cluster_json" | jq -r '.spec.bootstrap.recovery.recoveryTarget.backupID // ""')"
  read_lineage="$(printf '%s' "$cluster_json" | jq -r --arg source "$recovery_source" '.spec.externalClusters[] | select(.name == $source) | .plugin.parameters.serverName')"
  write_lineage="$(printf '%s' "$cluster_json" | jq -r '.spec.plugins[] | select(.name == "barman-cloud.cloudnative-pg.io") | .parameters.serverName')"
  write_version="${expected_write_lineage##*-}"
  expected_recovery_backup="$db_name-post-recovery-$write_version"
  recovery_backup="$(printf '%s' "$resources_json" | jq -r '[.[] | select(.apiVersion == "postgresql.cnpg.io/v1" and .kind == "Backup")][0].metadata.name // ""')"
  recovery_backup_method="$(printf '%s' "$resources_json" | jq -r '[.[] | select(.apiVersion == "postgresql.cnpg.io/v1" and .kind == "Backup")][0].spec.method // ""')"

  [ "$cluster_name" = "$db_name-database" ] || die "$db_name rendered Cluster name is $cluster_name"
  [ -n "$recovery_source" ] || die "$db_name does not render bootstrap.recovery"
  [ "$read_lineage" = "$expected_read_lineage" ] || \
    die "$db_name reads $read_lineage, expected $expected_read_lineage"
  [ "$backup_id" = "$expected_backup_id" ] || \
    die "$db_name pins $backup_id, expected $expected_backup_id"
  [ "$write_lineage" = "$expected_write_lineage" ] || \
    die "$db_name writes $write_lineage, expected $expected_write_lineage"
  [ "$read_lineage" != "$write_lineage" ] || die "$db_name recovery read/write lineages are identical"
  [ "$recovery_backup" = "$expected_recovery_backup" ] || \
    die "$db_name recovery Backup is $recovery_backup, expected $expected_recovery_backup"
  [ "$recovery_backup_method" = "plugin" ] || \
    die "$db_name recovery Backup does not use the Barman plugin"

  printf '    %-10s read=%-22s backup=%s write=%s\n' \
    "$db_name" "$read_lineage" "$backup_id" "$write_lineage"
}

assert_live_recovery_lineage() {
  db_name="$1"
  expected_read_lineage="$2"
  expected_backup_id="$3"
  expected_write_lineage="$4"
  cluster_name="$db_name-database"

  live_json="$(kubectl -n "$CNPG_NAMESPACE" get cluster "$cluster_name" -o json)"
  recovery_source="$(printf '%s' "$live_json" | jq -r '.spec.bootstrap.recovery.source // ""')"
  backup_id="$(printf '%s' "$live_json" | jq -r '.spec.bootstrap.recovery.recoveryTarget.backupID // ""')"
  read_lineage="$(printf '%s' "$live_json" | jq -r --arg source "$recovery_source" '.spec.externalClusters[]? | select(.name == $source) | .plugin.parameters.serverName')"
  write_lineage="$(printf '%s' "$live_json" | jq -r '.spec.plugins[]? | select(.name == "barman-cloud.cloudnative-pg.io") | .parameters.serverName')"

  [ "$read_lineage" = "$expected_read_lineage" ] && \
    [ "$backup_id" = "$expected_backup_id" ] && \
    [ "$write_lineage" = "$expected_write_lineage" ] || \
    die "existing Cluster/$cluster_name was not created from the prepared recovery manifest; refusing to mutate or delete it"
}

validate_postgres() {
  db_name="$1"
  expected_system_id="$2"
  database_name="$3"
  table_name="$4"
  cluster_name="$db_name-database"
  pod_name="$cluster_name-1"

  system_id="$(kubectl -n "$CNPG_NAMESPACE" exec "$pod_name" -c postgres -- \
    psql -U postgres -d postgres -Atqc 'select system_identifier from pg_control_system();')"
  [ "$system_id" = "$expected_system_id" ] || \
    die "$cluster_name system ID is $system_id, expected restored lineage $expected_system_id"

  row_count="$(kubectl -n "$CNPG_NAMESPACE" exec "$pod_name" -c postgres -- \
    psql -U postgres -d "$database_name" -Atqc "select count(*) from $table_name;")"
  case "$row_count" in
    ''|*[!0-9]*) die "$cluster_name returned invalid $table_name row count: $row_count" ;;
  esac
  [ "$row_count" -gt 0 ] || die "$cluster_name restored zero rows from $table_name"

  echo "    PostgreSQL system_identifier=$system_id"
  echo "    $database_name.$table_name rows=$row_count"
}

wait_for_application_healthy() {
  app_name="$1"
  deadline="$(deadline_after "$APP_TIMEOUT_SECONDS")"
  while true; do
    app_json="$(kubectl -n "$ARGO_NAMESPACE" get application "$app_name" -o json)"
    sync_status="$(printf '%s' "$app_json" | jq -r '.status.sync.status // "Unknown"')"
    health_status="$(printf '%s' "$app_json" | jq -r '.status.health.status // "Unknown"')"
    if [ "$sync_status" = "Synced" ] && [ "$health_status" = "Healthy" ]; then
      echo "    $app_name is Synced/Healthy"
      return 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      die "timed out waiting for $app_name Synced/Healthy (sync=$sync_status health=$health_status)"
    fi
    sleep 10
  done
}

cd "$ROOT_DIR"

log "Validating the pinned recovery contract"
while IFS='|' read -r db_name read_lineage backup_id write_lineage system_id database_name table_name consumer_app consumer_path; do
  assert_recovery_render "$db_name" "$read_lineage" "$backup_id" "$write_lineage"
done <<'EOF'
paperless|paperless-database-v6|20260728T050000|paperless-database-v9|7654249455955726366|paperless|documents_document|my-apps-paperless-ngx|my-apps/home/paperless-ngx
temporal|temporal-database-v8|20260728T030000|temporal-database-v11|7654249455983591452|temporal|executions|my-apps-temporal|my-apps/development/temporal
EOF

if [ "$EXECUTE" != true ]; then
  log "Preflight passed; no cluster changes made"
  echo "Current context: $(kubectl config current-context 2>/dev/null || echo unavailable)"
  echo "Run ./scripts/bootstrap-cnpg-recovery.sh --execute after Argo Waves 0-4 are ready."
  exit 0
fi

log "Pinning execution to the merged origin/main revision"
RECOVERY_REVISION="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
[ -n "$RECOVERY_REVISION" ] || die "could not resolve origin/main"
local_revision="$(git rev-parse HEAD)"
[ "$local_revision" = "$RECOVERY_REVISION" ] || \
  die "local HEAD $local_revision is not origin/main $RECOVERY_REVISION; pull the merged recovery revision first"
echo "    revision=$RECOVERY_REVISION"

log "Waiting for the CNPG controller"
wait_for_application database-cloudnative-pg-operator
wait_for_application cnpg-barman-plugin
wait_for_application database-postgres-global-secrets
wait_for_application_healthy database-cloudnative-pg-operator
wait_for_application_healthy cnpg-barman-plugin
wait_for_application_healthy database-postgres-global-secrets
kubectl wait --for=condition=Established crd/clusters.postgresql.cnpg.io --timeout="${APP_TIMEOUT_SECONDS}s"
kubectl wait --for=condition=Established crd/objectstores.barmancloud.cnpg.io --timeout="${APP_TIMEOUT_SECONDS}s"
kubectl -n "$CNPG_NAMESPACE" wait --for=condition=Available \
  deployment/cloudnative-pg-operator --timeout="${APP_TIMEOUT_SECONDS}s"
kubectl -n "$CNPG_NAMESPACE" wait --for=condition=Available \
  deployment/barman-cloud --timeout="${APP_TIMEOUT_SECONDS}s"

while IFS='|' read -r db_name read_lineage backup_id write_lineage system_id database_name table_name consumer_app consumer_path; do
  db_app="database-$db_name"
  db_path="infrastructure/database/cloudnative-pg/$db_name"
  cluster_name="$db_name-database"

  log "Recovering $db_name"
  assert_manual_application "$db_app" "$db_path"
  assert_manual_application "$consumer_app" "$consumer_path"

  if kubectl -n "$CNPG_NAMESPACE" get cluster "$cluster_name" >/dev/null 2>&1; then
    echo "    existing Cluster/$cluster_name found; verifying resumable recovery state"
    assert_live_recovery_lineage "$db_name" "$read_lineage" "$backup_id" "$write_lineage"
  else
    echo "    no existing Cluster/$cluster_name; fresh recovery creation is safe"
  fi

  sync_application "$db_app"
  wait_for_cluster_condition "$cluster_name" Ready "$CLUSTER_TIMEOUT_SECONDS"
  assert_live_recovery_lineage "$db_name" "$read_lineage" "$backup_id" "$write_lineage"
  validate_postgres "$db_name" "$system_id" "$database_name" "$table_name"
  wait_for_cluster_condition "$cluster_name" ContinuousArchiving "$CLUSTER_TIMEOUT_SECONDS"
  write_version="${write_lineage##*-}"
  wait_for_backup "$db_name-post-recovery-$write_version"
  wait_for_cluster_condition "$cluster_name" LastBackupSucceeded "$BACKUP_TIMEOUT_SECONDS"

  sync_application "$consumer_app"
  wait_for_application_healthy "$consumer_app"
done <<'EOF'
paperless|paperless-database-v6|20260728T050000|paperless-database-v9|7654249455955726366|paperless|documents_document|my-apps-paperless-ngx|my-apps/home/paperless-ngx
temporal|temporal-database-v8|20260728T030000|temporal-database-v11|7654249455983591452|temporal|executions|my-apps-temporal|my-apps/development/temporal
EOF

log "CNPG recovery accepted"
echo "All three databases match the audited PostgreSQL system IDs, contain application rows,"
echo "archive WAL, have completed a backup, and have Synced/Healthy consumers."
echo "Next GitOps step: flip the three database roots from overlays/recovery back to"
echo "overlays/initdb, commit that steady-state change, and sync the database Applications."
