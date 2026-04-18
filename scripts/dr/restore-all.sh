#!/usr/bin/env bash
# Parallel CNPG DR orchestrator — restores ALL databases under
# infrastructure/database/cloudnative-pg/<db>/ with lineage.yaml files.
#
# Each DB restores independently in its own log file. Failures in one DB do
# not abort others.
#
# Usage:
#   scripts/dr/restore-all.sh              # real run, parallelism 4
#   DRY_RUN=1 scripts/dr/restore-all.sh    # preview
#   CONCURRENCY=2 scripts/dr/restore-all.sh
#   scripts/dr/restore-all.sh gitea temporal   # only these DBs

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib/common.sh"

check_deps

CONCURRENCY="${CONCURRENCY:-4}"
DB_ROOT="$(repo_root)/infrastructure/database/cloudnative-pg"

# DB list: either positional args, or auto-discover directories containing lineage.yaml
if (( $# > 0 )); then
  DBS=("$@")
else
  mapfile -t DBS < <(find "$DB_ROOT" -mindepth 2 -maxdepth 2 -name lineage.yaml -exec dirname {} \; | xargs -n1 basename | sort)
fi

[[ ${#DBS[@]} -gt 0 ]] || die "no DBs to restore (nothing with lineage.yaml found)"

LOG_DIR=$(mktemp -d -t cnpg-dr-XXXXXX)
ok "restoring ${#DBS[@]} databases with concurrency $CONCURRENCY"
log "DBs:  ${DBS[*]}"
log "Logs: $LOG_DIR"

export DRY_RUN
SCRIPT_DIR_ABS="$SCRIPT_DIR"
export SCRIPT_DIR_ABS

# xargs-based parallelism — each DB gets its own log file
printf '%s\n' "${DBS[@]}" | xargs -n1 -P "$CONCURRENCY" -I {} bash -c '
  db="$1"
  log_file="$2/$db.log"
  echo "=== [$db] START $(date -u +%FT%TZ) ==="
  if "$SCRIPT_DIR_ABS/restore-one.sh" "$db" > "$log_file" 2>&1; then
    echo "=== [$db] ✓ DONE $(date -u +%FT%TZ)  (log: $log_file) ==="
  else
    echo "=== [$db] ✗ FAIL $(date -u +%FT%TZ)  (log: $log_file) ==="
  fi
' _ {} "$LOG_DIR"

echo ""
ok "all restore jobs finished. Review per-DB logs:"
ls -la "$LOG_DIR"
echo ""
log "NEXT STEPS:"
log "  1) Review git diff for lineage.yaml + cluster.yaml changes per DB"
log "  2) Commit: git add infrastructure/database/cloudnative-pg/*/{lineage,cluster}.yaml"
log "  3) Push"
log "  4) Unpause ArgoCD apps (listed at the end of each restore-one.sh log)"
