#!/usr/bin/env bash
# bootstrap-cluster.sh - repeatable platform prerequisites plus local Argo CD.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

GATEWAY_API_VERSION="v1.4.1"
GATEWAY_API_BASE_URL="https://github.com/kubernetes-sigs/gateway-api/releases/download/$GATEWAY_API_VERSION"
CILIUM_KUSTOMIZATION="$ROOT_DIR/clusters/talos/infra/cilium/kustomization.yaml"
CILIUM_VALUES="$ROOT_DIR/clusters/talos/infra/cilium/values.yaml"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/bootstrap-cluster.sh talos [--cilium=auto|install|skip] [--dry-run]
  ./scripts/bootstrap-cluster.sh openshift [--cilium=auto|skip] [--dry-run]
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

read_cilium_version() {
  awk '$1 == "version:" {gsub(/"/, "", $2); print $2; exit}' "$CILIUM_KUSTOMIZATION"
}

read_cilium_cluster_name() {
  awk '
    /^cluster:/ { in_cluster = 1; next }
    in_cluster && $1 == "name:" { print $2; exit }
  ' "$CILIUM_VALUES"
}

select_cilium_command() {
  if command -v cilium >/dev/null 2>&1; then
    CILIUM_CMD="cilium"
  elif command -v cilium-cli >/dev/null 2>&1; then
    CILIUM_CMD="cilium-cli"
  else
    die "Cilium CLI not found; install either cilium or cilium-cli"
  fi
}

install_cilium() {
  select_cilium_command
  echo "Installing Cilium $CILIUM_VERSION for cluster $CILIUM_CLUSTER_NAME..."
  "$CILIUM_CMD" install \
    --version "$CILIUM_VERSION" \
    --set "cluster.name=$CILIUM_CLUSTER_NAME" \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=true \
    --set 'securityContext.capabilities.ciliumAgent={CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}' \
    --set 'securityContext.capabilities.cleanCiliumState={NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}' \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set k8sServiceHost=localhost \
    --set k8sServicePort=7445 \
    --set hubble.enabled=false \
    --set hubble.relay.enabled=false \
    --set hubble.ui.enabled=false \
    --set gatewayAPI.enabled=true \
    --set gatewayAPI.enableAlpn=true \
    --set gatewayAPI.enableAppProtocol=true
}

verify_cilium() {
  select_cilium_command
  echo "Verifying Cilium health and pinned version..."
  "$CILIUM_CMD" status --wait --wait-duration 2m

  local running_image
  local running_version
  running_image="$(
    kubectl get daemonset cilium -n kube-system \
      -o jsonpath='{.spec.template.spec.containers[0].image}'
  )"
  running_version="$(sed -E 's/.*:v([0-9]+\.[0-9]+\.[0-9]+).*/\1/' <<<"$running_image")"

  if [ "$running_version" != "$CILIUM_VERSION" ]; then
    die "Cilium version mismatch: running=$running_version expected=$CILIUM_VERSION"
  fi
}

install_talos_gateway_api_crds() {
  echo "Installing pinned upstream Gateway API CRDs..."
  kubectl apply -f "$GATEWAY_API_BASE_URL/standard-install.yaml"
  kubectl apply --server-side -f "$GATEWAY_API_BASE_URL/experimental-install.yaml"
}

verify_openshift_gateway_api() {
  echo "Verifying OpenShift-managed Gateway API CRDs..."
  kubectl get crd gatewayclasses.gateway.networking.k8s.io
  kubectl get crd gateways.gateway.networking.k8s.io
  kubectl get crd httproutes.gateway.networking.k8s.io

  local subscriptions
  subscriptions="$(
    kubectl get subscriptions.operators.coreos.com -A \
      -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.spec.name}{"\t"}{.spec.channel}{"\t"}{.status.installedCSV}{"\n"}{end}'
  )"

  if awk -F '\t' '$2 == "servicemeshoperator" { found = 1 } END { exit !found }' <<<"$subscriptions"; then
    die "OpenShift Service Mesh Operator v2 conflicts with the OpenShift Gateway API implementation"
  fi
}

verify_secret_gate() {
  local missing=0
  local name
  local namespace
  local secret

  for secret in \
    "1passwordconnect/1password-credentials" \
    "1passwordconnect/1password-operator-token" \
    "external-secrets/1passwordconnect"
  do
    namespace="${secret%%/*}"
    name="${secret#*/}"
    if ! kubectl get secret -n "$namespace" "$name" >/dev/null 2>&1; then
      echo "Missing required bootstrap secret: $secret" >&2
      missing=1
    fi
  done

  if [ "$missing" -ne 0 ]; then
    echo "Pre-seed the three 1Password secrets using README.md Step 3, then rerun:" >&2
    echo "  ./scripts/bootstrap-cluster.sh $PROFILE --cilium=$CILIUM_MODE" >&2
    exit 1
  fi
}

print_dry_run() {
  echo "Profile: $PROFILE"
  if [ "$PROFILE" = "talos" ]; then
    case "$CILIUM_MODE" in
      auto)
        echo "Cilium: install if absent; verify pinned version if present ($CILIUM_VERSION, $CILIUM_CLUSTER_NAME)"
        ;;
      install)
        echo "Cilium: install pinned version $CILIUM_VERSION for $CILIUM_CLUSTER_NAME"
        ;;
      skip)
        echo "Cilium: skipped by operator override"
        ;;
    esac
    echo "Gateway API: apply $GATEWAY_API_BASE_URL/standard-install.yaml"
    echo "Gateway API: apply server-side $GATEWAY_API_BASE_URL/experimental-install.yaml"
  else
    echo "Cilium: skipped for OpenShift"
    echo "Gateway API: verify platform CRDs"
    echo "OSSM v2: verify no conflicting subscription"
  fi

  echo "Secret gate: verify 1passwordconnect/1password-credentials"
  echo "Secret gate: verify 1passwordconnect/1password-operator-token"
  echo "Secret gate: verify external-secrets/1passwordconnect"
  echo "Run: $SCRIPT_DIR/bootstrap-argocd.sh $PROFILE"
}

PROFILE="${1:-}"
if [ -z "$PROFILE" ] || [ "$PROFILE" = "-h" ] || [ "$PROFILE" = "--help" ]; then
  usage
  [ -n "$PROFILE" ] && exit 0
  exit 1
fi
shift

case "$PROFILE" in
  talos|openshift) ;;
  *) die "unknown cluster profile '$PROFILE'; expected talos or openshift" ;;
esac

CILIUM_MODE="auto"
DRY_RUN=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --cilium=auto|--cilium=install|--cilium=skip)
      CILIUM_MODE="${1#--cilium=}"
      ;;
    --dry-run)
      DRY_RUN=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
  shift
done

if [ "$PROFILE" = "openshift" ] && [ "$CILIUM_MODE" = "install" ]; then
  die "--cilium=install is invalid for the openshift profile"
fi

CILIUM_VERSION=""
CILIUM_CLUSTER_NAME=""
if [ "$PROFILE" = "talos" ]; then
  CILIUM_VERSION="$(read_cilium_version)"
  CILIUM_CLUSTER_NAME="$(read_cilium_cluster_name)"
  [ -n "$CILIUM_VERSION" ] || die "could not read Cilium version from $CILIUM_KUSTOMIZATION"
  [ -n "$CILIUM_CLUSTER_NAME" ] || die "could not read Cilium cluster name from $CILIUM_VALUES"
fi

if [ "$DRY_RUN" = true ]; then
  print_dry_run
  exit 0
fi

require_command kubectl
require_command helm
require_command openssl

if [ "$PROFILE" = "talos" ]; then
  if [ "$CILIUM_MODE" != "skip" ]; then
    select_cilium_command
  fi
  case "$CILIUM_MODE" in
    auto)
      if kubectl get daemonset cilium -n kube-system >/dev/null 2>&1; then
        verify_cilium
      else
        install_cilium
      fi
      ;;
    install)
      install_cilium
      ;;
    skip)
      echo "Skipping Cilium actions by operator override."
      ;;
  esac
  install_talos_gateway_api_crds
else
  verify_openshift_gateway_api
fi

verify_secret_gate
"$SCRIPT_DIR/bootstrap-argocd.sh" "$PROFILE"
