#!/usr/bin/env bash
# Emergency: Remove all Kyverno webhooks to unblock cluster recovery
# Run this when the cluster is in a webhook deadlock (pods can't be created)
# Kyverno will recreate its webhooks once it starts successfully.
set -euo pipefail

echo "WARNING: This will delete ALL Kyverno webhook configurations."
echo "Kyverno will recreate them once it starts successfully."
echo ""
read -p "Continue? (yes/no): " confirm
[[ "$confirm" == "yes" ]] || exit 1

echo "Deleting Kyverno validating webhooks..."
kubectl delete validatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno --ignore-not-found

echo "Deleting Kyverno mutating webhooks..."
kubectl delete mutatingwebhookconfigurations -l app.kubernetes.io/instance=kyverno --ignore-not-found

echo ""
echo "Done. Monitor Kyverno pods: kubectl get pods -n kyverno -w"
echo "Webhooks will be recreated when Kyverno admission controller is healthy."
