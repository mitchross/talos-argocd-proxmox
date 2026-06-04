#!/usr/bin/env bash
set -euo pipefail

# Focused Argo CD bootstrap step.
# Prefer scripts/bootstrap-cluster.sh for the complete platform-aware workflow.
# Direct invocation assumes networking, Gateway API, and secret prerequisites
# are already complete.
#
# Usage:
#   ./scripts/bootstrap-argocd.sh [talos|openshift]
#
# Prerequisites:
#   1. kubectl access to the target cluster
#   2. Platform prerequisites completed
#   3. 1Password secrets pre-seeded in the target cluster

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

CLUSTER="${1:-talos}"
case "$CLUSTER" in
  talos|openshift)
    ;;
  *)
    echo "❌ Unknown cluster '$CLUSTER'. Expected one of: talos, openshift"
    exit 1
    ;;
esac

BOOTSTRAP_DIR="$ROOT_DIR/clusters/$CLUSTER/bootstrap"
ARGOCD_NAMESPACE_FILE="$BOOTSTRAP_DIR/ns.yaml"
ARGOCD_VALUES_FILE="$BOOTSTRAP_DIR/values.yaml"
ARGOCD_ROOT_FILE="$BOOTSTRAP_DIR/root.yaml"
ARGOCD_CHART_VERSION="9.5.17"

echo "🚀 Bootstrapping ArgoCD for $CLUSTER with sync waves..."

if [ ! -f "$ARGOCD_NAMESPACE_FILE" ] || [ ! -f "$ARGOCD_VALUES_FILE" ] || [ ! -f "$ARGOCD_ROOT_FILE" ]; then
  echo "❌ Missing bootstrap files under $BOOTSTRAP_DIR"
  exit 1
fi

echo ""
echo "📦 Creating argocd namespace..."
kubectl apply -f "$ARGOCD_NAMESPACE_FILE"

# values.yaml disables the chart's redis-secret-init hook. On a fresh cluster
# the Secret is absent, so Redis crashes with `secret "argocd-redis" not found`
# and the install wedges. Create it idempotently before Helm.
echo ""
echo "🔑 Ensuring argocd-redis auth secret exists..."
if ! kubectl get secret argocd-redis -n argocd > /dev/null 2>&1; then
  kubectl create secret generic argocd-redis -n argocd \
    --from-literal=auth="$(openssl rand -base64 32)"
  echo "   ✅ created argocd-redis"
else
  echo "   ✅ argocd-redis already present"
fi

echo ""
echo "⎈ Installing ArgoCD via Helm..."
if ! helm upgrade --install argocd argo-cd \
  --repo https://argoproj.github.io/argo-helm \
  --version "$ARGOCD_CHART_VERSION" \
  --namespace argocd \
  --values "$ARGOCD_VALUES_FILE" \
  --wait \
  --timeout 10m \
  --set 'configs.secret.argocdServerAdminPassword=$2a$10$KjM2oz7Et5Ai9JLB4mry6.rfFF0IJfCWuaD2XJ/2sr6oQGcszf8cO'; then
  # On a re-run, Helm can fail with an SSA conflict on argocd-secret after
  # argocd-server has written admin password metadata. Continue only if ArgoCD
  # is already running and ready to self-manage.
  if kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=10s > /dev/null 2>&1; then
    echo "⚠️  Helm reported a conflict, but argocd-server is already Available."
    echo "    This is expected on a re-run — continuing to self-management."
  else
    echo "❌ Helm install failed and argocd-server is not Available. Aborting."
    exit 1
  fi
fi

echo ""
echo "⏳ Waiting for ArgoCD CRDs to be established..."
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io

echo ""
echo "⏳ Waiting for ArgoCD server to be available..."
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s

echo ""
echo "🔄 Deploying root application (enables self-management)..."
kubectl apply -f "$ARGOCD_ROOT_FILE"

echo ""
echo "✅ ArgoCD bootstrap complete for $CLUSTER!"
echo ""
echo "📊 ArgoCD will now sync applications in cluster-specific waves."
if [ "$CLUSTER" = "talos" ]; then
  echo "   Wave 0: Cilium, ArgoCD, 1Password Connect, External Secrets"
  echo "   Wave 1: cert-manager, Longhorn, Snapshot Controller, VolSync"
  echo "   Wave 2: pvc-plumber + VolSync backup cluster"
  echo "   Wave 3: CNPG Barman Plugin"
  echo "   Wave 4: Infrastructure AppSet + Database AppSet + custom entrypoints"
  echo "   Wave 5: OpenTelemetry core + Monitoring AppSet"
  echo "   Wave 6: Observability overlays + Talos Apps AppSet"
else
  echo "   Wave 0: ArgoCD, 1Password Connect, External Secrets"
  echo "   Wave 1: cert-manager, OpenShift LVM storage"
  echo "   Wave 4: OpenShift infrastructure AppSet"
  echo "   Wave 6: OpenShift apps AppSet"
fi
echo ""
echo "🔍 Monitor progress with:"
echo "   kubectl get applications -n argocd -w"
echo ""
echo "🌐 Access ArgoCD UI:"
echo "   kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "   Open: https://localhost:8080"
echo ""
echo "🔑 Admin password is pre-configured via Helm values (no initial-admin-secret needed)"
echo ""
