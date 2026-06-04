#!/usr/bin/env bash
# validate-bootstrap-profiles.sh - prove bootstrap dry-run profile behavior.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_SCRIPT="$SCRIPT_DIR/bootstrap-cluster.sh"
FAKE_BIN="$(mktemp -d)"

cleanup() {
  rm -rf "$FAKE_BIN"
}
trap cleanup EXIT

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

assert_contains() {
  local output="$1"
  local expected="$2"
  grep -Fq -- "$expected" <<<"$output" ||
    fail "expected dry-run output to contain: $expected"
}

assert_excludes() {
  local output="$1"
  local unexpected="$2"
  if grep -Fq -- "$unexpected" <<<"$output"; then
    fail "expected dry-run output to exclude: $unexpected"
  fi
}

for command in kubectl helm cilium cilium-cli; do
  printf '#!/usr/bin/env bash\nexit 99\n' >"$FAKE_BIN/$command"
  chmod +x "$FAKE_BIN/$command"
done

run_dry() {
  PATH="$FAKE_BIN:$PATH" bash "$BOOTSTRAP_SCRIPT" "$@"
}

echo "=== Bootstrap Profile Validation ==="

talos_output="$(run_dry talos --dry-run)"
assert_contains "$talos_output" "Cilium: install if absent; verify pinned version if present"
assert_contains "$talos_output" "gateway-api/releases/download/v1.4.1/standard-install.yaml"
assert_contains "$talos_output" "gateway-api/releases/download/v1.4.1/experimental-install.yaml"
assert_contains "$talos_output" "Secret gate: verify 1passwordconnect/1password-credentials"
assert_contains "$talos_output" "Secret gate: verify 1passwordconnect/1password-operator-token"
assert_contains "$talos_output" "Secret gate: verify external-secrets/1passwordconnect"
assert_contains "$(tail -n 1 <<<"$talos_output")" "bootstrap-argocd.sh talos"

openshift_output="$(run_dry openshift --dry-run)"
assert_contains "$openshift_output" "Cilium: skipped for OpenShift"
assert_excludes "$openshift_output" "gateway-api/releases/download/v1.4.1"
assert_contains "$openshift_output" "Gateway API: verify platform CRDs"
assert_contains "$openshift_output" "OSSM v2: verify no conflicting subscription"
assert_contains "$openshift_output" "Secret gate: verify 1passwordconnect/1password-credentials"
assert_contains "$openshift_output" "Secret gate: verify 1passwordconnect/1password-operator-token"
assert_contains "$openshift_output" "Secret gate: verify external-secrets/1passwordconnect"
assert_contains "$(tail -n 1 <<<"$openshift_output")" "bootstrap-argocd.sh openshift"

if run_dry openshift --cilium=install --dry-run >/dev/null 2>&1; then
  fail "openshift --cilium=install --dry-run must fail"
fi

if run_dry unknown --dry-run >/dev/null 2>&1; then
  fail "unknown profile must fail"
fi

echo "PASSED: bootstrap profile dry-runs are non-mutating and platform-correct"
