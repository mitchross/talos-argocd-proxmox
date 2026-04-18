#!/usr/bin/env bash
# Render an ephemeral recovery manifest for a single CNPG Cluster.
#
# Reads cluster.yaml + lineage.yaml and produces a manifest that:
#   - Keeps the existing bootstrap.initdb (validation annotation lets both coexist)
#   - Adds bootstrap.recovery.source pointing at an externalClusters entry
#   - Adds externalClusters[] referencing restoreFromServerName
#   - Optionally sets bootstrap.recovery.recoveryTarget.targetTime for PITR
#   - Updates backup.barmanObjectStore.serverName to currentServerName
#
# Usage:
#   render-recovery.sh <db>
# Prints the rendered manifest to stdout.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

[[ $# -eq 1 ]] || die "usage: render-recovery.sh <db>"
DB="$1"

CLUSTER_YAML="$(cluster_yaml_path "$DB")"
LINEAGE="$(lineage_path "$DB")"

[[ -f "$CLUSTER_YAML" ]] || die "cluster.yaml not found: $CLUSTER_YAML"
[[ -f "$LINEAGE"      ]] || die "lineage.yaml not found: $LINEAGE"

# Pull lineage + shared barman config into env for yq strenv()
export SRC_NAME="${DB}-recovery-source"
export RESTORE_FROM="$(yq -r '.restoreFromServerName' "$LINEAGE")"
export CURRENT="$(yq -r '.currentServerName' "$LINEAGE")"
export TARGET="$(yq -r '.restoreTarget' "$LINEAGE")"
export DEST_PATH="$(yq -r '.spec.backup.barmanObjectStore.destinationPath' "$CLUSTER_YAML")"
export ENDPOINT="$(yq -r '.spec.backup.barmanObjectStore.endpointURL' "$CLUSTER_YAML")"
export AK_SEC="$(yq -r '.spec.backup.barmanObjectStore.s3Credentials.accessKeyId.name' "$CLUSTER_YAML")"
export AK_KEY="$(yq -r '.spec.backup.barmanObjectStore.s3Credentials.accessKeyId.key' "$CLUSTER_YAML")"
export SK_SEC="$(yq -r '.spec.backup.barmanObjectStore.s3Credentials.secretAccessKey.name' "$CLUSTER_YAML")"
export SK_KEY="$(yq -r '.spec.backup.barmanObjectStore.s3Credentials.secretAccessKey.key' "$CLUSTER_YAML")"

[[ -n "$RESTORE_FROM" && "$RESTORE_FROM" != "null" ]] || die "lineage.yaml missing restoreFromServerName"
[[ -n "$CURRENT"      && "$CURRENT" != "null"      ]] || die "lineage.yaml missing currentServerName"

# First pass — apply the definite mutations
TMP1=$(mktemp -t cnpg-render-XXXX.yaml)
trap 'rm -f "$TMP1"' EXIT

yq '
  .spec.bootstrap.recovery.source = strenv(SRC_NAME)
  | .spec.externalClusters = [{
      "name": strenv(SRC_NAME),
      "barmanObjectStore": {
        "serverName":     strenv(RESTORE_FROM),
        "destinationPath": strenv(DEST_PATH),
        "endpointURL":    strenv(ENDPOINT),
        "s3Credentials": {
          "accessKeyId":     {"name": strenv(AK_SEC), "key": strenv(AK_KEY)},
          "secretAccessKey": {"name": strenv(SK_SEC), "key": strenv(SK_KEY)}
        },
        "wal": {"compression": "gzip"}
      }
    }]
  | .spec.backup.barmanObjectStore.serverName = strenv(CURRENT)
' "$CLUSTER_YAML" > "$TMP1"

# Second pass — conditionally add PITR recoveryTarget.targetTime
if [[ "$TARGET" != "latest" && -n "$TARGET" && "$TARGET" != "null" ]]; then
  yq '.spec.bootstrap.recovery.recoveryTarget.targetTime = strenv(TARGET)' "$TMP1"
else
  cat "$TMP1"
fi
