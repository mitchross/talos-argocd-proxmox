#!/usr/bin/env bash
set -euo pipefail

# Bootstrap ArgoCD Script
# This script works around kustomize --enable-helm compatibility issues
# by using Helm directly, then letting ArgoCD self-manage
#
# Prerequisites:
#   1. Gateway API CRDs must be applied
#   2. Cilium must be installed (provides CNI networking)
#   3. 1Password secrets must be pre-seeded
#
# See README.md for the full bootstrap sequence.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Expected Cilium version — must match infrastructure/networking/cilium/kustomization.yaml
EXPECTED_CILIUM_VERSION="$(awk '
  $1 == "version:" { version = $2 }
  END {
    if (version == "") exit 1
    print version
  }
' "$ROOT_DIR/infrastructure/networking/cilium/kustomization.yaml")"
EXPECTED_CILIUM_CLUSTER_NAME="talos-singlenode-gpu-prod"

if command -v cilium > /dev/null 2>&1; then
  CILIUM_CMD="cilium"
elif command -v cilium-cli > /dev/null 2>&1; then
  CILIUM_CMD="cilium-cli"
else
  CILIUM_CMD=""
fi

echo "🚀 Bootstrapping ArgoCD with sync waves..."

# Pre-flight: Verify Cilium is installed and healthy at the correct version
echo ""
echo "🔍 Pre-flight: Checking Cilium..."

if [ -z "$CILIUM_CMD" ]; then
  echo "❌ Cilium CLI not found. Install either 'cilium' or 'cilium-cli' first: https://docs.cilium.io/en/stable/gettingstarted/k8s-install-default/"
  exit 1
fi

if ! "$CILIUM_CMD" status --wait --wait-duration 30s &> /dev/null; then
  echo "❌ Cilium is not healthy. Install Cilium first:"
  echo ""
  echo "   $CILIUM_CMD install \\"
  echo "       --version $EXPECTED_CILIUM_VERSION \\"
  echo "       --set cluster.name=$EXPECTED_CILIUM_CLUSTER_NAME \\"
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
  echo "     $CILIUM_CMD uninstall"
  echo "     $CILIUM_CMD install --version $EXPECTED_CILIUM_VERSION \\"
  echo "         --set cluster.name=$EXPECTED_CILIUM_CLUSTER_NAME \\"
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

# Step 1.5: Ensure the argocd-redis auth secret exists.
# values.yaml disables the chart's redis-secret-init hook (it assumes the
# Secret already exists from a prior install). On a FRESH cluster that Secret
# is absent, so redis crashes with `secret "argocd-redis" not found` and the
# whole install wedges. Create it idempotently here so a destroy/recreate
# bootstrap runs unattended. (Bit us on the 2026-06-01 nuke/recreate.)
echo ""
echo "🔑 Ensuring argocd-redis auth secret exists..."
if ! kubectl get secret argocd-redis -n argocd > /dev/null 2>&1; then
  kubectl create secret generic argocd-redis -n argocd \
    --from-literal=auth="$(openssl rand -base64 32)"
  echo "   ✅ created argocd-redis"
else
  echo "   ✅ argocd-redis already present"
fi

# Step 2: Install ArgoCD using Helm
echo ""
echo "⎈ Installing ArgoCD via Helm..."
# shellcheck disable=SC2016 # The bcrypt hash must remain literal.
if ! helm upgrade --install argocd argo-cd \
  --repo https://argoproj.github.io/argo-helm \
  --version 9.7.0 \
  --namespace argocd \
  --values "$ROOT_DIR/infrastructure/controllers/argocd/values.yaml" \
  --wait \
  --timeout 10m \
  --set 'configs.secret.argocdServerAdminPassword=$2a$10$KjM2oz7Et5Ai9JLB4mry6.rfFF0IJfCWuaD2XJ/2sr6oQGcszf8cO'; then
  # On a RE-RUN over an already-running ArgoCD, helm can fail with a
  # server-side-apply conflict on argocd-secret (.data.admin.passwordMtime is
  # owned by argocd-server once the admin password is used). That's benign:
  # ArgoCD self-management (root.yaml below) owns argocd-secret via
  # ServerSideApply=true. Only abort if ArgoCD isn't actually running.
  if kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=10s > /dev/null 2>&1; then
    echo "⚠️  Helm reported a conflict, but argocd-server is already Available."
    echo "    This is expected on a re-run — continuing to self-management (root.yaml)."
  else
    echo "❌ Helm install failed and argocd-server is not Available. Aborting."
    exit 1
  fi
fi

# Step 3: Wait for CRDs to be established
echo ""
echo "⏳ Waiting for ArgoCD CRDs to be established..."
kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io

# Step 4: Wait for ArgoCD server to be ready
echo ""
echo "⏳ Waiting for ArgoCD server to be available..."
kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s

# Step 5: HTTPRoute deploys automatically with Gateway at Wave 4
# (moved to infrastructure/networking/gateway/ to avoid bootstrap deadlock)

# Step 6: Apply root application to start GitOps self-management
echo ""
echo "🔄 Deploying root application (enables self-management)..."
kubectl apply -f "$ROOT_DIR/infrastructure/controllers/argocd/root.yaml"

echo ""
echo "✅ ArgoCD bootstrap complete!"
echo ""
echo "📊 ArgoCD will now sync applications in this order:"
echo "   Wave 0: Cilium (networking), 1Password Connect, External Secrets"
echo "   Wave 1: Longhorn (storage), Snapshot Controller, VolSync, pvc-plumber v2 operator"
echo "   Wave 2: pvc-plumber webhook configs (FAIL-CLOSED PVC admission gate)"
echo "   Wave 3: CNPG Barman Plugin (database backup plugin)"
echo "   Wave 4: Infrastructure AppSet (cert-manager, GPU operators, gateway, etc.) + Database AppSet"
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
echo "🔑 Admin password is pre-configured via Helm values (no initial-admin-secret needed)"
echo ""
