#!/usr/bin/env bash
# Force every backup-labeled PVC's ReplicationSource to fire NOW so the
# first post-v3-cutover backup lands in the new RustFS S3 repo.
#
# Background: VolSync's `spec.trigger.manual` field fires a scheduled RS
# out-of-band. Bumping it to a fresh value tells the controller to run one
# sync. Once the manual run has landed, remove the field again so the cron
# schedule resumes; otherwise the RS can sit in WaitingForManual forever.
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
# Usage:
#   ./scripts/trigger-fresh-volsync-baselines.sh [--dry-run]
#   ./scripts/trigger-fresh-volsync-baselines.sh --clear-manual [--dry-run]

set -euo pipefail

DRY=false
CLEAR=false
TRIGGER="post-v3-cutover-$(date +%s)"

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY=true
      ;;
    --clear-manual)
      CLEAR=true
      ;;
    -h|--help)
      sed -n '1,28p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ "$CLEAR" == true ]]; then
  readarray -t RSES < <(kubectl get replicationsource -A -o json | \
    jq -r '.items[] | select(.spec.trigger.manual != null) | "\(.metadata.namespace)/\(.metadata.name)"')

  [[ "${#RSES[@]}" -gt 0 ]] || { echo "no ReplicationSources with trigger.manual found"; exit 0; }

  echo "found ${#RSES[@]} ReplicationSources with trigger.manual, will remove it"
  [[ "$DRY" == true ]] && { printf '  %s\n' "${RSES[@]}"; exit 0; }

  for RS in "${RSES[@]}"; do
    NS=${RS%%/*}
    NAME=${RS##*/}
    printf '  %-50s ... ' "$RS"
    if kubectl patch replicationsource -n "$NS" "$NAME" \
      --type=json -p='[{"op":"remove","path":"/spec/trigger/manual"}]' \
      >/dev/null 2>&1; then
      echo "cleared"
    else
      echo "FAILED"
    fi
  done

  echo
  echo "now watch:  watch 'kubectl get rs -A'"
  echo "scheduled sources should move from WaitingForManual to WaitingForSchedule with nextSyncTime set"
  exit 0
fi

readarray -t RSES < <(kubectl get replicationsource -A -o json | \
  jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name)"')

[[ "${#RSES[@]}" -gt 0 ]] || { echo "no ReplicationSources found"; exit 1; }

echo "found ${#RSES[@]} ReplicationSources, will set trigger.manual=$TRIGGER"
[[ "$DRY" == true ]] && { printf '  %s\n' "${RSES[@]}"; exit 0; }

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
echo "after the triggered runs finish, resume schedules with:  $0 --clear-manual"
