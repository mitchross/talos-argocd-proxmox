#!/usr/bin/env bash
set -euo pipefail

# Bootstrap ArgoCD Script
# This script works around kustomize --enable-helm compatibility issues
# by using Helm directly, then letting ArgoCD self-manage
#
# Prerequisites:
#   1. Cilium must be installed FIRST (provides CNI networking)
#   2. Gateway API CRDs must be applied
#   3. 1Password secrets must be pre-seeded
#
# See README.md for the full bootstrap sequence.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Expected Cilium version — must match infrastructure/networking/cilium/kustomization.yaml
EXPECTED_CILIUM_VERSION="1.19.0"

echo "🚀 Bootstrapping ArgoCD with sync waves..."

# Pre-flight: Verify Cilium is installed and healthy at the correct version
echo ""
echo "🔍 Pre-flight: Checking Cilium..."

if ! command -v cilium &> /dev/null; then
  echo "❌ cilium CLI not found. Install it first: https://docs.cilium.io/en/stable/gettingstarted/k8s-install-default/"
  exit 1
fi

if ! cilium status --wait --wait-duration 30s &> /dev/null; then
  echo "❌ Cilium is not healthy. Install Cilium first:"
  echo ""
  echo "   cilium install \\"
  echo "       --version $EXPECTED_CILIUM_VERSION \\"
  echo "       --set cluster.name=talos-prod-cluster \\"
  echo "       --set ipam.mode=kubernetes \\"
  echo "       --set kubeProxyReplacement=true \\"
  echo "       --set k8sServiceHost=localhost \\"
  echo "       --set k8sServicePort=7445 \\"
  echo "       --set hubble.enabled=false \\"
  echo "       --set hubble.relay.enabled=false \\"
  echo "       --set hubble.ui.enabled=false \\"
  echo "       --set gatewayAPI.enabled=true"
  echo ""
  exit 1
fi

RUNNING_VERSION=$(kubectl get ds cilium -n kube-system -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | sed -E 's/.*:v([0-9]+\.[0-9]+\.[0-9]+).*/\1/' || true)

if [ -n "$RUNNING_VERSION" ] && [ "$RUNNING_VERSION" != "$EXPECTED_CILIUM_VERSION" ]; then
  echo "⚠️  WARNING: Cilium version mismatch!"
  echo "   Running:  $RUNNING_VERSION"
  echo "   Expected: $EXPECTED_CILIUM_VERSION (from Helm chart)"
  echo ""
  echo "   ArgoCD Wave 0 will upgrade Cilium $RUNNING_VERSION → $EXPECTED_CILIUM_VERSION"
  echo "   This in-place upgrade can corrupt BPF state and break new pod networking."
  echo ""
  echo "   Recommended: Reinstall Cilium at the correct version first:"
  echo "     cilium uninstall"
  echo "     cilium install --version $EXPECTED_CILIUM_VERSION \\"
  echo "         --set cluster.name=talos-prod-cluster \\"
  echo "         --set ipam.mode=kubernetes \\"
  echo "         --set kubeProxyReplacement=true \\"
  echo "         --set k8sServiceHost=localhost \\"
  echo "         --set k8sServicePort=7445 \\"
  echo "         --set hubble.enabled=false \\"
  echo "         --set hubble.relay.enabled=false \\"
  echo "         --set hubble.ui.enabled=false \\"
  echo "         --set gatewayAPI.enabled=true"
  echo ""
  read -p "   Continue anyway? (y/N) " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
else
  echo "✅ Cilium $RUNNING_VERSION is healthy and matches Helm chart ($EXPECTED_CILIUM_VERSION)"
fi

# Step 1: Create namespace
echo ""
echo "📦 Creating argocd namespace..."
kubectl apply -f "$ROOT_DIR/infrastructure/controllers/argocd/ns.yaml"

# Step 2: Install ArgoCD using Helm
echo ""
echo "⎈ Installing ArgoCD via Helm..."
helm upgrade --install argocd argo-cd \
  --repo https://argoproj.github.io/argo-helm \
  --version 9.3.0 \
  --namespace argocd \
  --values "$ROOT_DIR/infrastructure/controllers/argocd/values.yaml" \
  --wait \
  --timeout 10m

# Step 3: Wait for CRDs to be established
echo ""
echo "⏳ Waiting for ArgoCD CRDs to be established..."
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io

# Step 4: Wait for ArgoCD server to be ready
echo ""
echo "⏳ Waiting for ArgoCD server to be available..."
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s

# Step 5: Apply HTTPRoute (if it exists)
if [ -f "$ROOT_DIR/infrastructure/controllers/argocd/http-route.yaml" ]; then
  echo ""
  echo "🌐 Applying HTTPRoute..."
  kubectl apply -f "$ROOT_DIR/infrastructure/controllers/argocd/http-route.yaml"
fi

# Step 6: Apply root application to start GitOps self-management
echo ""
echo "🔄 Deploying root application (enables self-management)..."
kubectl apply -f "$ROOT_DIR/infrastructure/controllers/argocd/root.yaml"

echo ""
echo "✅ ArgoCD bootstrap complete!"
echo ""
echo "📊 ArgoCD will now sync applications in this order:"
echo "   Wave 0: Cilium (networking), 1Password Connect, External Secrets"
echo "   Wave 1: Longhorn (storage), Snapshot Controller, VolSync"
echo "   Wave 2: PVC Plumber (backup checker, FAIL-CLOSED gate)"
echo "   Wave 3: Kyverno (policy engine, must register webhooks before app PVCs)"
echo "   Wave 4: Infrastructure AppSet (cert-manager, GPU operators, gateway, etc.)"
echo "   Wave 5: Monitoring AppSet (Prometheus, Grafana, Loki)"
echo "   Wave 6: My-Apps AppSet (user workloads)"
echo ""
echo "🔍 Monitor progress with:"
echo "   kubectl get applications -n argocd -w"
echo ""
echo "🌐 Access ArgoCD UI:"
echo "   kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "   Open: https://localhost:8080"
echo ""
echo "🔑 Get admin password:"
echo "   kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
echo ""
