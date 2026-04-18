#!/usr/bin/env bash
# Post-restore lineage bump. Updates BOTH lineage.yaml and cluster.yaml so
# they stay in sync: the next backup cycle writes to the bumped serverName.
#
# Usage: lineage-bump.sh <db>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib/common.sh"

[[ $# -eq 1 ]] || die "usage: lineage-bump.sh <db>"
DB="$1"

LINEAGE="$(lineage_path "$DB")"
CLUSTER="$(cluster_yaml_path "$DB")"

[[ -f "$LINEAGE" ]] || die "no lineage.yaml for $DB"
[[ -f "$CLUSTER" ]] || die "no cluster.yaml for $DB"

PREV=$(yq -r '.currentServerName' "$LINEAGE")
NEXT=$(next_serverName "$PREV")
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log "[$DB] bumping lineage: $PREV → $NEXT (restoreFrom → $PREV)"

# 1) Update lineage.yaml
yq -i "
  .restoreFromServerName = \"$PREV\"
  | .currentServerName   = \"$NEXT\"
  | .restoreTarget       = \"latest\"
  | .lastRestored        = \"$NOW\"
  | .firstBoot           = false
" "$LINEAGE"

# 2) Update cluster.yaml backup.serverName to match new currentServerName.
#    (The rendered recovery manifest already writes to $CURRENT/$NEXT in-cluster;
#    this keeps git-declared state in sync so ArgoCD doesn't drift.)
yq -i "
  .spec.backup.barmanObjectStore.serverName = \"$NEXT\"
" "$CLUSTER"

ok "[$DB] lineage bumped. Commit both files: lineage.yaml + cluster.yaml"
