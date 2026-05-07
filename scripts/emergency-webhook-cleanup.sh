#!/usr/bin/env bash
# Emergency: Remove pvc-plumber webhook configurations to unblock cluster
# recovery. Run this when the cluster is in a webhook deadlock — symptoms:
# PVC creation hangs cluster-wide, Longhorn/argocd/cnpg pods can't mount
# storage, Argo apps stuck Progressing forever.
#
# pvc-plumber will recreate its webhook configurations from the
# infrastructure/controllers/pvc-plumber/webhooks.yaml manifest as soon as
# ArgoCD next syncs the application.
#
# History: this script originally existed to recover from the 2026-04-08
# Kyverno webhook deadlock incident. Kyverno was removed from the cluster
# on 2026-05-07. The same recovery pattern applies to any admission webhook
# with failurePolicy: Fail — pvc-plumber's `validate-pvc` (the data-safety
# gate, fail-closed by design) is the current concrete instance.
set -euo pipefail

echo "WARNING: This will delete ALL pvc-plumber webhook configurations."
echo "pvc-plumber will recreate them on the next ArgoCD sync."
echo ""
read -p "Continue? (yes/no): " confirm
[[ "$confirm" == "yes" ]] || exit 1

# The MutatingWebhookConfiguration `pvc-plumber` carries both `mutate-pvc`
# and `mutate-job` entries; deleting the single named MWC removes them
# both. Same for the ValidatingWebhookConfiguration which carries both
# `validate-pvc` and `validate-pvc-exempt` entries.
echo "Deleting pvc-plumber validating webhook configuration..."
kubectl delete validatingwebhookconfiguration pvc-plumber --ignore-not-found

echo "Deleting pvc-plumber mutating webhook configuration..."
kubectl delete mutatingwebhookconfiguration pvc-plumber --ignore-not-found

echo ""
echo "Done. Monitor pvc-plumber pods: kubectl get pods -n volsync-system -l app.kubernetes.io/name=pvc-plumber -w"
echo "Webhooks will be recreated when ArgoCD next syncs the pvc-plumber Application."
