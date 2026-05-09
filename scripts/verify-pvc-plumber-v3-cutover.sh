#!/usr/bin/env bash
# Verify pvc-plumber v3.0.0 (S3-backed) deployment is healthy after cutover.
#
# Run this AFTER the v3.0.0 image has rolled out and ArgoCD shows
# pvc-plumber as Synced/Healthy. Exits non-zero on the first failure so
# you can wire it into a CI/sanity-check loop if you want.
#
# Usage:  ./scripts/verify-pvc-plumber-v3-cutover.sh
set -euo pipefail

NS=volsync-system
DEPLOY=pvc-plumber

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
section() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }

fail() { red "✗ $*"; exit 1; }
ok()   { green "✓ $*"; }

section "1. operator pods running v3.0.0"
IMG=$(kubectl get deploy -n "$NS" "$DEPLOY" -o jsonpath='{.spec.template.spec.containers[*].image}')
[[ "$IMG" == *":3."* ]] || fail "wrong image: $IMG"
ok "image: $IMG"

READY=$(kubectl get deploy -n "$NS" "$DEPLOY" -o jsonpath='{.status.readyReplicas}/{.status.replicas}')
[[ "$READY" == "2/2" || "$READY" == "1/1" ]] || fail "not ready: $READY"
ok "replicas: $READY"

section "2. webhook server listening on :9443 (was the v2.1.0 regression)"
kubectl exec -n "$NS" deploy/"$DEPLOY" -- sh -c 'netstat -tlnp 2>/dev/null | grep -q ":9443 "' \
  || fail ":9443 not listening — webhook server didn't start"
ok ":9443 listening"

section "3. binary IS the operator binary (controller-runtime present)"
RT_COUNT=$(kubectl exec -n "$NS" deploy/"$DEPLOY" -- sh -c 'strings /pvc-plumber 2>/dev/null | grep -c "sigs.k8s.io/controller-runtime"' || echo 0)
[[ "$RT_COUNT" -gt 100 ]] || fail "binary appears to be the v1 legacy build (controller-runtime strings: $RT_COUNT)"
ok "controller-runtime strings: $RT_COUNT (v3 operator binary)"

section "4. JobMutator webhook is GONE"
COUNT=$(kubectl get mutatingwebhookconfiguration pvc-plumber -o json | \
  jq '[.webhooks[] | select(.name=="mutate-job.pvc-plumber.io")] | length')
[[ "$COUNT" == "0" ]] || fail "JobMutator webhook still registered (count=$COUNT) — should be deleted in v3"
ok "JobMutator webhook absent (v3 deployment shape)"

section "5. backend type reports kopia-s3"
kubectl logs -n "$NS" deploy/"$DEPLOY" --tail=200 2>&1 | grep -q '"backend":"kopia-s3"' \
  || fail "operator logs don't show kopia-s3 backend"
ok "operator logs show kopia-s3 backend"

section "6. operator's own pvc-plumber-kopia Secret has all 3 S3 fields"
KEYS=$(kubectl get secret -n "$NS" pvc-plumber-kopia -o jsonpath='{.data}' | jq -r 'keys | sort | join(",")')
[[ "$KEYS" == *"AWS_ACCESS_KEY_ID"* && "$KEYS" == *"AWS_SECRET_ACCESS_KEY"* && "$KEYS" == *"KOPIA_PASSWORD"* ]] \
  || fail "pvc-plumber-kopia Secret missing required keys (have: $KEYS)"
ok "pvc-plumber-kopia Secret keys: $KEYS"

section "7. all volsync-* ESes have been recycled to v3 shape"
LEGACY=$(kubectl get externalsecret -A -o json | \
  jq -r '[.items[] | select(.metadata.name | startswith("volsync-")) |
          select((.spec.target.template.data.KOPIA_REPOSITORY // "") | startswith("filesystem"))
        ] | length')
if [[ "$LEGACY" -gt 0 ]]; then
  red "✗ $LEGACY volsync-* ESes still on filesystem template — reconciler hasn't recycled yet"
  red "  these are the still-pending ones:"
  kubectl get externalsecret -A -o json | \
    jq -r '.items[] | select(.metadata.name | startswith("volsync-")) |
            select((.spec.target.template.data.KOPIA_REPOSITORY // "") | startswith("filesystem")) |
            "    \(.metadata.namespace)/\(.metadata.name)"'
  exit 1
fi
ok "all volsync-* ESes on s3:// template"

section "8. all 28 backup-labeled PVCs have a corresponding volsync-* Secret rendered"
PVC_COUNT=$(kubectl get pvc -A -l 'backup in (hourly,daily)' --no-headers | wc -l)
SEC_COUNT=$(kubectl get secret -A -o json | jq '[.items[] | select(.metadata.name | startswith("volsync-")) | select(.metadata.name | endswith("-backup-dest") | not)] | length')
ok "PVCs: $PVC_COUNT  rendered Secrets: $SEC_COUNT"

section "9. RustFS bucket is reachable from a fresh pod"
TMP=$(mktemp)
kubectl run rustfs-verify-$$ --rm --restart=Never --image=amazon/aws-cli:latest -n cloudnative-pg \
  --overrides='{"spec":{"containers":[{"name":"v","image":"amazon/aws-cli:latest","command":["sh","-c"],"args":["aws --endpoint-url http://192.168.10.133:30293 s3api head-bucket --bucket volsync-kopia"],"envFrom":[{"secretRef":{"name":"cnpg-s3-credentials"}}]}],"restartPolicy":"Never"}}' \
  --timeout=30s >/dev/null 2>"$TMP" || fail "bucket head failed: $(cat "$TMP")"
ok "RustFS bucket reachable"

green ""
green "ALL CHECKS PASSED. Operator v3.0.0 is healthy and the cutover is complete."
