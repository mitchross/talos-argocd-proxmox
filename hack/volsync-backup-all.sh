#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: hack/volsync-backup-all.sh [--execute] [--namespace NAMESPACE] [--selector LABEL_SELECTOR]

Triggers every selected VolSync ReplicationSource by patching
spec.trigger.manual to pre-dr-<timestamp>. Defaults to dry-run.

Examples:
  hack/volsync-backup-all.sh
  hack/volsync-backup-all.sh --execute --namespace jellyfin
  hack/volsync-backup-all.sh --execute --selector 'volsync.backup/pvc=config'
EOF
}

execute=false
namespace_args=(-A)
selector_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      execute=true
      shift
      ;;
    --namespace|-n)
      namespace_args=(-n "$2")
      shift 2
      ;;
    --selector|-l)
      selector_args=(-l "$2")
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

trigger="pre-dr-$(date -u +%Y%m%dT%H%M%SZ)"
mapfile -t sources < <(
  kubectl get replicationsources "${namespace_args[@]}" "${selector_args[@]}" \
    -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.sourcePVC}{"\n"}{end}'
)

if [[ ${#sources[@]} -eq 0 ]]; then
  echo "No ReplicationSources matched."
  exit 0
fi

for source in "${sources[@]}"; do
  IFS=$'\t' read -r ns name pvc <<<"$source"
  if [[ "$execute" == "true" ]]; then
    kubectl patch replicationsource -n "$ns" "$name" --type merge \
      -p "{\"spec\":{\"trigger\":{\"manual\":\"$trigger\"}}}"
  else
    echo "DRY-RUN would patch $ns/$name sourcePVC=$pvc manual=$trigger"
  fi
done

if [[ "$execute" != "true" ]]; then
  echo
  echo "Dry run only. Re-run with --execute to trigger backups."
fi
