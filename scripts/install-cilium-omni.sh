#!/usr/bin/env bash
set -euo pipefail

# Cilium Installation Script for Omni-Managed Cluster
# This script installs Cilium CNI with proper Omni configuration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 Installing Cilium CNI for Omni-Managed Cluster"
echo "=================================================="
echo ""

# Check kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Check cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to cluster. Check your kubeconfig."
    echo "   Try: export KUBECONFIG=~/.kube/config"
    exit 1
fi

echo "✅ Cluster connection verified"
echo ""

# Step 1: Install Gateway API CRDs
echo "📦 Step 1: Installing Gateway API CRDs..."
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/experimental-install.yaml

echo "⏳ Waiting for Gateway API CRDs to be established..."
kubectl wait --for condition=established --timeout=60s \
    crd/gatewayclasses.gateway.networking.k8s.io \
    crd/gateways.gateway.networking.k8s.io \
    crd/httproutes.gateway.networking.k8s.io

echo "✅ Gateway API CRDs installed"
echo ""

# Step 2: Install Cilium
echo "📦 Step 2: Installing Cilium CNI..."
echo "   - Cluster Name: talos-proxmox-prod"
echo "   - Routing Mode: native (better performance)"
echo "   - API Endpoint: 192.168.10.100:6443 (Omni load balancer)"
echo "   - Pod CIDR: 10.14.0.0/16"
echo ""

cd "$REPO_ROOT"
kubectl kustomize infrastructure/networking/cilium --enable-helm | kubectl apply -f -

echo "⏳ Waiting for Cilium to be ready..."
sleep 5

# Wait for Cilium operator to be ready
kubectl wait --for=condition=Available deployment/cilium-operator -n kube-system --timeout=300s

echo "✅ Cilium operator is ready"
echo ""

# Wait for Cilium DaemonSet to be ready
echo "⏳ Waiting for Cilium agents to be ready..."
kubectl rollout status daemonset/cilium -n kube-system --timeout=300s

echo "✅ Cilium agents are ready"
echo ""

# Step 3: Verify Installation
echo "🔍 Step 3: Verifying Cilium Installation..."
echo ""

# Check Cilium status
echo "Cilium Status:"
kubectl exec -n kube-system ds/cilium -- cilium-dbg status --brief || true
echo ""

# Check routing mode
echo "Routing Mode:"
kubectl exec -n kube-system ds/cilium -- cilium-dbg status | grep -i "routing mode" || echo "  Check manually with: kubectl exec -n kube-system ds/cilium -- cilium-dbg status"
echo ""

# Check nodes
echo "Node Status:"
kubectl get nodes -o wide
echo ""

# Check Cilium pods
echo "Cilium Pods:"
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium
echo ""

# Check LoadBalancer IP pools
echo "LoadBalancer IP Pools:"
kubectl get ciliumloadbalancerippool -n kube-system || echo "  No IP pools configured yet (this is normal)"
echo ""

echo "✅ Cilium Installation Complete!"
echo ""
echo "📋 Next Steps:"
echo "   1. Verify nodes show 'Ready' status"
echo "   2. Check Omni dashboard for cluster health"
echo "   3. Bootstrap ArgoCD to deploy applications:"
echo "      cd $REPO_ROOT"
echo "      kustomize build infrastructure/controllers/argocd --enable-helm | kubectl apply -f -"
echo "      kubectl wait --for condition=established --timeout=60s crd/applications.argoproj.io"
echo "      kubectl wait --for=condition=Available deployment/argocd-server -n argocd --timeout=300s"
echo "      kubectl apply -f infrastructure/controllers/argocd/root.yaml"
echo ""
echo "🎉 Happy clustering!"
