#!/usr/bin/env bash
# restart-all-pods.sh - Restart workload-managed pods for app workloads.
#
# This intentionally restarts controllers (Deployments, StatefulSets, and
# DaemonSets) instead of deleting Pods directly. Controller rollouts preserve the
# Kubernetes ownership model and avoid deleting completed Job pods or unmanaged
# one-off Pods that may not come back.
#
# Default scope is ArgoCD Applications in the monitoring and my-apps projects.
# That skips cluster infrastructure, ArgoCD itself, databases, and controllers.
#
# Examples:
#   ./scripts/restart-all-pods.sh --dry-run
#   ./scripts/restart-all-pods.sh --yes
#   ./scripts/restart-all-pods.sh --namespace dozzle --yes --wait
#   ./scripts/restart-all-pods.sh --yes --wait --timeout 30m
#   ./scripts/restart-all-pods.sh --projects monitoring,my-apps --yes
#   ./scripts/restart-all-pods.sh --all-namespaces --exclude-namespace-regex '^(kube-system|argocd)$' --dry-run

set -euo pipefail

DRY_RUN=false
YES=false
WAIT=false
NAMESPACE=""
SELECTOR=""
EXCLUDE_NAMESPACE_REGEX=""
PROJECTS="monitoring,my-apps"
ALL_NAMESPACES=false
TIMEOUT="30m"

usage() {
  sed -n '2,32p' "$0"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --yes|-y)
      YES=true
      shift
      ;;
    --wait)
      WAIT=true
      shift
      ;;
    --timeout)
      [[ $# -ge 2 ]] || die "--timeout requires a kubectl duration value"
      TIMEOUT="$2"
      shift 2
      ;;
    --namespace|-n)
      [[ $# -ge 2 ]] || die "--namespace requires a value"
      NAMESPACE="$2"
      shift 2
      ;;
    --projects)
      [[ $# -ge 2 ]] || die "--projects requires a comma-separated value"
      PROJECTS="$2"
      shift 2
      ;;
    --all-namespaces)
      ALL_NAMESPACES=true
      shift
      ;;
    --selector|-l)
      [[ $# -ge 2 ]] || die "--selector requires a value"
      SELECTOR="$2"
      shift 2
      ;;
    --exclude-namespace-regex)
      [[ $# -ge 2 ]] || die "--exclude-namespace-regex requires a value"
      EXCLUDE_NAMESPACE_REGEX="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown arg: $1"
      ;;
  esac
done

command -v kubectl >/dev/null 2>&1 || die "kubectl is required"

if [[ "$DRY_RUN" == false && "$YES" == false ]]; then
  die "refusing to restart workloads without --yes. Run with --dry-run first to inspect scope."
fi

if [[ -n "$NAMESPACE" && "$ALL_NAMESPACES" == true ]]; then
  die "--namespace and --all-namespaces cannot be used together"
fi

KUBECTL_SCOPE=()
if [[ -n "$NAMESPACE" ]]; then
  KUBECTL_SCOPE=(-n "$NAMESPACE")
else
  KUBECTL_SCOPE=(-A)
fi

KUBECTL_SELECTOR=()
if [[ -n "$SELECTOR" ]]; then
  KUBECTL_SELECTOR=(-l "$SELECTOR")
fi

WORKLOAD_KINDS=("deployment" "statefulset" "daemonset")
TMP_WORKLOADS="$(mktemp)"
TMP_APPS="$(mktemp)"
TMP_NAMESPACES="$(mktemp)"
trap 'rm -f "$TMP_WORKLOADS" "$TMP_APPS" "$TMP_NAMESPACES"' EXIT

if [[ -z "$NAMESPACE" && "$ALL_NAMESPACES" == false ]]; then
  kubectl -n argocd get applications.argoproj.io \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.project}{"\t"}{.spec.destination.namespace}{"\n"}{end}' \
    | awk -F'\t' -v projects="$PROJECTS" '
      BEGIN {
        split(projects, p, ",")
        for (i in p) wanted[p[i]] = 1
      }
      wanted[$2] {
        print $1 "\t" $3
      }
    ' | sort -u > "$TMP_APPS"

  awk -F'\t' '{print $1}' "$TMP_APPS" | sort -u > "$TMP_APPS.names"
  mv "$TMP_APPS.names" "$TMP_APPS"

  kubectl -n argocd get applications.argoproj.io \
    -o jsonpath='{range .items[*]}{.spec.project}{"\t"}{.spec.destination.namespace}{"\n"}{end}' \
    | awk -F'\t' -v projects="$PROJECTS" '
      BEGIN {
        split(projects, p, ",")
        for (i in p) wanted[p[i]] = 1
      }
      wanted[$1] && $2 != "" {
        print $2
      }
    ' | sort -u > "$TMP_NAMESPACES"

  if [[ ! -s "$TMP_APPS" && ! -s "$TMP_NAMESPACES" ]]; then
    die "no ArgoCD Applications found for projects: $PROJECTS"
  fi
fi

for kind in "${WORKLOAD_KINDS[@]}"; do
  kubectl get "$kind" "${KUBECTL_SCOPE[@]}" "${KUBECTL_SELECTOR[@]}" \
    -o go-template='{{range .items}}{{.kind}}{{"\t"}}{{.metadata.namespace}}{{"\t"}}{{.metadata.name}}{{"\t"}}{{index .metadata.labels "argocd.argoproj.io/instance"}}{{"\n"}}{{end}}' \
    2>/dev/null || true
done | while IFS=$'\t' read -r kind namespace name argo_instance; do
  [[ -n "$kind" && -n "$namespace" && -n "$name" ]] || continue
  if [[ -n "$EXCLUDE_NAMESPACE_REGEX" && "$namespace" =~ $EXCLUDE_NAMESPACE_REGEX ]]; then
    continue
  fi
  if [[ -z "$NAMESPACE" && "$ALL_NAMESPACES" == false ]]; then
    namespace_match=false
    app_match=false
    if grep -Fxq "$namespace" "$TMP_NAMESPACES"; then
      namespace_match=true
    fi
    if [[ -n "$argo_instance" ]] && grep -Fxq "$argo_instance" "$TMP_APPS"; then
      app_match=true
    fi
    if [[ "$namespace_match" == false && "$app_match" == false ]]; then
      continue
    fi
  fi
  printf '%s\t%s\t%s\n' "$kind" "$namespace" "$name"
done | sort -k2,2 -k1,1 -k3,3 > "$TMP_WORKLOADS"

if [[ ! -s "$TMP_WORKLOADS" ]]; then
  echo "No matching workload controllers found."
  exit 0
fi

if [[ -z "$NAMESPACE" && "$ALL_NAMESPACES" == false ]]; then
  echo "Scope: ArgoCD Application projects: $PROJECTS"
elif [[ -n "$NAMESPACE" ]]; then
  echo "Scope: namespace $NAMESPACE"
else
  echo "Scope: all namespaces"
fi
echo
echo "Workloads selected for restart:"
column -t -s $'\t' "$TMP_WORKLOADS"
echo

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run only. Re-run with --yes to restart these workload controllers."
  exit 0
fi

echo "Restarting selected workload controllers..."
while IFS=$'\t' read -r kind namespace name; do
  api_kind="$(tr '[:upper:]' '[:lower:]' <<< "$kind")"
  echo "restart ${api_kind}/${name} -n ${namespace}"
  kubectl -n "$namespace" rollout restart "${api_kind}/${name}"
done < "$TMP_WORKLOADS"

if [[ "$WAIT" == true ]]; then
  echo
  echo "Waiting for rollouts to complete (timeout per workload: $TIMEOUT)..."
  while IFS=$'\t' read -r kind namespace name; do
    api_kind="$(tr '[:upper:]' '[:lower:]' <<< "$kind")"
    echo "wait ${api_kind}/${name} -n ${namespace}"
    kubectl -n "$namespace" rollout status "${api_kind}/${name}" --timeout="$TIMEOUT"
  done < "$TMP_WORKLOADS"
fi

echo
echo "Restart requests submitted."
