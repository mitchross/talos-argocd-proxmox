#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat >"$TMP/kubectl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >>"$KUBECTL_CALLS"
printf '\n' >>"$KUBECTL_CALLS"

if [[ "$*" == "get replicationsource -A -o json" ]]; then
  cat <<'JSON'
{
  "items": [
    {
      "metadata": {"namespace": "app-a", "name": "data-backup"},
      "spec": {"trigger": {"manual": "stale-manual", "schedule": "0 * * * *"}}
    },
    {
      "metadata": {"namespace": "app-b", "name": "cache-backup"},
      "spec": {"trigger": {"schedule": "0 2 * * *"}}
    }
  ]
}
JSON
  exit 0
fi

if [[ "$1" == "patch" ]]; then
  exit 0
fi

echo "unexpected kubectl call: $*" >&2
exit 1
SH
chmod +x "$TMP/kubectl"

export PATH="$TMP:$PATH"
export KUBECTL_CALLS="$TMP/kubectl.calls"

"$ROOT/scripts/trigger-fresh-volsync-baselines.sh" --clear-manual >"$TMP/out"

grep -q "app-a/data-backup" "$TMP/out"
! grep -q "app-b/cache-backup" "$TMP/out"
grep -q -- '--type=json' "$KUBECTL_CALLS"
grep -q -- 'op.*remove.*path.*spec/trigger/manual' "$KUBECTL_CALLS"

echo "trigger-fresh-volsync-baselines tests passed"
