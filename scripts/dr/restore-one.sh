#!/usr/bin/env bash
# Single-DB CNPG DR orchestrator (Path A — validation-annotation flow).
#
# Given a DB name (matching a directory under
# infrastructure/database/cloudnative-pg/<db>/), this script:
#   1. Reads lineage.yaml
#   2. Pauses ArgoCD for the DB app (+ consumer app if present)
#   3. Deletes the live Cluster + all its PVCs
#   4. Applies the rendered recovery manifest (dual-bootstrap with validation disabled)
#   5. Waits for the cluster to report Ready
#   6. Runs a validation command (custom per-DB if <db>-dir/validate.sh exists, else psql ping)
#   7. Bumps lineage.yaml + cluster.yaml to the next lineage version
#   8. Leaves ArgoCD paused for you to verify git before un-pausing manually
#
# Usage:
#   scripts/dr/restore-one.sh <db>
# Example:
#   scripts/dr/restore-one.sh gitea
#
# Environment:
#   DRY_RUN=1   Print actions without executing
#   CLUSTER_TIMEOUT=<sec>  How long to wait for Ready (default 900)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

check_deps

[[ $# -eq 1 ]] || die "usage: restore-one.sh <db>"
DB="$1"
DRY_RUN="${DRY_RUN:-0}"
TIMEOUT="${CLUSTER_TIMEOUT:-900}"

DIR="$(db_dir "$DB")"
[[ -d "$DIR"                  ]] || die "no directory for db '$DB' at $DIR"
[[ -f "$DIR/lineage.yaml"     ]] || die "no lineage.yaml for $DB"
[[ -f "$DIR/cluster.yaml"     ]] || die "no cluster.yaml for $DB"

FIRST_BOOT="$(lineage_get "$DB" firstBoot)"
CLUSTER_NAME="$(lineage_get "$DB" clusterName)"
NAMESPACE="$(lineage_get "$DB" namespace)"
RESTORE_FROM="$(lineage_get "$DB" restoreFromServerName)"
CURRENT="$(lineage_get "$DB" currentServerName)"
TARGET="$(lineage_get "$DB" restoreTarget)"

step "[$DB] lineage: $RESTORE_FROM → $CURRENT  (target: $TARGET)  firstBoot=$FIRST_BOOT"

if [[ "$FIRST_BOOT" == "true" ]]; then
  log "[$DB] firstBoot=true — applying cluster.yaml as-is via kubectl (ArgoCD would do this anyway)"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "  (dry-run) kubectl apply -f $DIR/cluster.yaml"
  else
    kubectl apply -f "$DIR/cluster.yaml"
  fi
  ok "[$DB] done (no restore needed)"
  exit 0
fi

# ---------- Phase: pause ArgoCD ---------------------------------------------
step "[$DB] pausing ArgoCD"
mapfile -t APPS < <(argocd_apps_for_db "$DB")
if (( ${#APPS[@]} == 0 )); then
  warn "[$DB] no ArgoCD apps matched '$DB' or 'my-apps-$DB' — proceeding uncautiously"
else
  for app in "${APPS[@]}"; do
    if [[ "$DRY_RUN" == "1" ]]; then
      echo "  (dry-run) pause $app"
    else
      argocd_pause "$app"
      log "[$DB] paused $app"
    fi
  done
fi

# ---------- Phase: delete live Cluster + PVCs -------------------------------
step "[$DB] deleting live Cluster + PVCs"
if kubectl -n "$NAMESPACE" get cluster "$CLUSTER_NAME" >/dev/null 2>&1; then
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "  (dry-run) kubectl delete cluster $CLUSTER_NAME -n $NAMESPACE"
  else
    kubectl -n "$NAMESPACE" delete cluster "$CLUSTER_NAME" --wait=false
    kubectl wait --for=delete -n "$NAMESPACE" "cluster/$CLUSTER_NAME" --timeout=120s 2>/dev/null || true
  fi
fi

# CNPG preserves PVCs on cluster delete. They must be removed so the recovery
# cluster starts with fresh volumes and runs barman-cloud-restore.
if [[ "$DRY_RUN" == "1" ]]; then
  echo "  (dry-run) kubectl delete pvc -n $NAMESPACE -l cnpg.io/cluster=$CLUSTER_NAME"
else
  kubectl -n "$NAMESPACE" delete pvc -l "cnpg.io/cluster=$CLUSTER_NAME" --ignore-not-found
  # Wait for actual disappearance (Longhorn reclaim can take 30+ sec)
  for i in 1 2 3 4 5 6 7 8 9; do
    remaining=$(kubectl -n "$NAMESPACE" get pvc -l "cnpg.io/cluster=$CLUSTER_NAME" --no-headers 2>/dev/null | wc -l || echo 0)
    [[ "$remaining" -eq 0 ]] && break
    log "[$DB] waiting for $remaining PVC(s) to terminate (attempt $i/9)..."
    sleep 10
  done
fi
ok "[$DB] cluster + PVCs gone"

# ---------- Phase: render + apply recovery manifest -------------------------
step "[$DB] rendering + applying recovery manifest"
RECOVERY=$(mktemp -t "${DB}-recovery-XXXXXX.yaml")
trap 'rm -f "$RECOVERY"' EXIT

"$SCRIPT_DIR/lib/render-recovery.sh" "$DB" > "$RECOVERY"

# Quick sanity: must contain both initdb and recovery, must have our source name
grep -q "recovery:" "$RECOVERY" || die "rendered manifest missing bootstrap.recovery"
grep -q "${DB}-recovery-source" "$RECOVERY" || die "rendered manifest missing externalClusters name"

log "[$DB] rendered manifest: $RECOVERY"
if [[ "$DRY_RUN" == "1" ]]; then
  echo "--- BEGIN RECOVERY MANIFEST ---"
  cat "$RECOVERY"
  echo "--- END RECOVERY MANIFEST ---"
  log "[$DB] dry-run stop"
  exit 0
fi

# Path A uses kubectl apply (not create) — the validation annotation on the
# Cluster metadata lets CNPG's admission webhook accept the dual-bootstrap form.
kubectl apply -f "$RECOVERY"

# ---------- Phase: wait for Ready -------------------------------------------
step "[$DB] waiting for Cluster Ready (up to ${TIMEOUT}s)"
if ! "$SCRIPT_DIR/lib/wait-ready.sh" "$CLUSTER_NAME" "$NAMESPACE" "$TIMEOUT"; then
  warn "[$DB] did not reach Ready — dumping status"
  kubectl -n "$NAMESPACE" describe cluster "$CLUSTER_NAME" 2>&1 | tail -40 >&2
  die "[$DB] restore FAILED"
fi

# ---------- Phase: validate -------------------------------------------------
step "[$DB] validating"
if [[ -x "$DIR/validate.sh" ]]; then
  log "[$DB] running per-DB validator $DIR/validate.sh"
  if ! "$DIR/validate.sh"; then
    die "[$DB] validation FAILED"
  fi
else
  # Generic: connect + count tables
  count=$(kubectl exec -n "$NAMESPACE" "${CLUSTER_NAME}-1" -c postgres -- \
    psql -U postgres -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
  log "[$DB] restored DB has $count public tables"
  [[ "$count" -gt 0 ]] || warn "[$DB] 0 tables in public schema — this may indicate empty restore"
fi

# ---------- Phase: bump lineage ---------------------------------------------
step "[$DB] bumping lineage"
"$SCRIPT_DIR/lineage-bump.sh" "$DB"

# ---------- Done ------------------------------------------------------------
ok "[$DB] RESTORE COMPLETE"
log "[$DB] ArgoCD is STILL PAUSED. Next steps:"
log "  1) git diff $DIR/{cluster,lineage}.yaml — review serverName bump"
log "  2) git add + commit + push"
log "  3) ArgoCD will show Synced (bootstrap diff is already in ignoreDifferences)"
log "  4) Unpause: kubectl -n argocd annotate application <app> argocd.argoproj.io/skip-reconcile- --overwrite"
log "     Apps to unpause: ${APPS[*]:-<none>}"
