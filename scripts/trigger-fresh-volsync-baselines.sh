#!/usr/bin/env bash
# Force every backup-labeled PVC's ReplicationSource to fire NOW so the
# first post-v3-cutover backup lands in the new RustFS S3 repo.
#
# Background: VolSync's `spec.trigger.manual` field is the way to fire a
# scheduled RS out-of-band. Bumping it to a fresh value tells the
# controller "trigger one sync, then wait for the next manual update".
# We use this here to compress the post-cutover validation window from
# "wait up to one hour for the schedule" down to "everything backs up
# now, in parallel".
#
# Run this AFTER verify-pvc-plumber-v3-cutover.sh passes. Watch progress
# with:
#   watch 'kubectl get rs -A | grep -v WaitingForManual'
#
# Each mover Job uploads its full PVC contents to S3 the first time
# (kopia is content-addressed; subsequent runs are incremental). Total
# wall time depends on dataset sizes and 10G fabric — the largest PVCs
# (immich/library 300Gi, project-nomad/nomad-storage 120Gi) will
# dominate.
#
# Usage:  ./scripts/trigger-fresh-volsync-baselines.sh [--dry-run]

set -euo pipefail

DRY=${1:-}
TRIGGER="post-v3-cutover-$(date +%s)"

readarray -t RSES < <(kubectl get replicationsource -A -o json | \
  jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name)"')

[[ "${#RSES[@]}" -gt 0 ]] || { echo "no ReplicationSources found"; exit 1; }

echo "found ${#RSES[@]} ReplicationSources, will set trigger.manual=$TRIGGER"
[[ "$DRY" == "--dry-run" ]] && { printf '  %s\n' "${RSES[@]}"; exit 0; }

for RS in "${RSES[@]}"; do
  NS=${RS%%/*}
  NAME=${RS##*/}
  printf '  %-50s ... ' "$RS"
  if kubectl patch replicationsource -n "$NS" "$NAME" \
    --type=merge -p "{\"spec\":{\"trigger\":{\"manual\":\"$TRIGGER\"}}}" \
    >/dev/null 2>&1; then
    echo "triggered"
  else
    echo "FAILED"
  fi
done

echo
echo "now watch:  watch 'kubectl get rs -A'"
echo "successful run will show lastSyncTime advancing past pre-cutover timestamps"
echo "first kopia init against the new bucket will be slowest; subsequent runs are incremental"
