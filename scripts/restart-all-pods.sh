#!/usr/bin/env bash
# restart-all-pods.sh - Restart workload-managed pods for app workloads.
#
# This intentionally restarts controllers (Deployments, StatefulSets, and
# DaemonSets) instead of deleting Pods directly. Controller rollouts preserve the
# Kubernetes ownership model and avoid deleting completed Job pods or unmanaged
# one-off Pods that may not come back.
#
# Default scope is ArgoCD Applications in the infrastructure, monitoring, and my-apps projects.
#
# Examples:
#   ./scripts/restart-all-pods.sh --dry-run
#   ./scripts/restart-all-pods.sh --yes
#   ./scripts/restart-all-pods.sh --namespace dozzle --yes --wait
#   ./scripts/restart-all-pods.sh --yes --wait --timeout 30m
#   ./scripts/restart-all-pods.sh --projects monitoring,my-apps --yes
#   ./scripts/restart-all-pods.sh --all-namespaces --exclude-namespace-regex '^(kube-system|argocd)$' --dry-run
#   ./scripts/restart-all-pods.sh --yes --parallel 8 --wait          # parallel restarts
#   ./scripts/restart-all-pods.sh --app immich --yes                 # single app
#   ./scripts/restart-all-pods.sh --app-regex '.*-pdf$' --yes        # regex app filter

set -euo pipefail

DRY_RUN=false
YES=false
WAIT=false
NAMESPACE=""
SELECTOR=""
EXCLUDE_NAMESPACE_REGEX=""
PROJECTS="infrastructure,monitoring,my-apps"
ALL_NAMESPACES=false
TIMEOUT="30m"
PARALLEL=1
APP_FILTER=""
APP_REGEX=""

usage() {
  sed -n '2,33p' "$0"
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
    --parallel|-j)
      [[ $# -ge 2 ]] || die "--parallel requires a number"
      PARALLEL="$2"
      shift 2
      ;;
    --app)
      [[ $# -ge 2 ]] || die "--app requires an ArgoCD application name"
      APP_FILTER="$2"
      shift 2
      ;;
    --app-regex)
      [[ $# -ge 2 ]] || die "--app-regex requires a regex pattern"
      APP_REGEX="$2"
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
TMP_RESULTS="$(mktemp)"
TMP_WAIT_FAIL="$(mktemp)"
trap 'rm -f "$TMP_WORKLOADS" "$TMP_APPS" "$TMP_NAMESPACES" "$TMP_RESULTS" "$TMP_WAIT_FAIL"' EXIT

# Build namespace and app lists from ArgoCD projects (unless --namespace or --all-namespaces)
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

# Discover and filter workloads
for kind in "${WORKLOAD_KINDS[@]}"; do
  kubectl get "$kind" ${KUBECTL_SCOPE[@]} ${KUBECTL_SELECTOR[@]+"${KUBECTL_SELECTOR[@]}"} \
    -o go-template='{{range .items}}{{.kind}}{{"\t"}}{{.metadata.namespace}}{{"\t"}}{{.metadata.name}}{{"\t"}}{{index .metadata.labels "argocd.argoproj.io/instance"}}{{"\n"}}{{end}}' \
    2>/dev/null || true
done | while IFS=$'\t' read -r kind namespace name argo_instance; do
  [[ -n "$kind" && -n "$namespace" && -n "$name" ]] || continue

  # Exclude namespace regex
  if [[ -n "$EXCLUDE_NAMESPACE_REGEX" && "$namespace" =~ $EXCLUDE_NAMESPACE_REGEX ]]; then
    continue
  fi

  # ArgoCD project scope filter (not --namespace, not --all-namespaces)
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

  # --app exact filter (matches ArgoCD instance label OR namespace)
  if [[ -n "$APP_FILTER" ]]; then
    app_match=false
    [[ -n "$argo_instance" && "$argo_instance" == "$APP_FILTER" ]] && app_match=true
    [[ "$namespace" == "$APP_FILTER" ]] && app_match=true
    [[ "$app_match" == false ]] && continue
  fi

  # --app-regex filter (matches ArgoCD instance label OR namespace)
  if [[ -n "$APP_REGEX" ]]; then
    app_match=false
    [[ -n "$argo_instance" && "$argo_instance" =~ $APP_REGEX ]] && app_match=true
    [[ "$namespace" =~ $APP_REGEX ]] && app_match=true
    [[ "$app_match" == false ]] && continue
  fi

  printf '%s\t%s\t%s\n' "$kind" "$namespace" "$name"
done | sort -k2,2 -k1,1 -k3,3 > "$TMP_WORKLOADS"

if [[ ! -s "$TMP_WORKLOADS" ]]; then
  echo "No matching workload controllers found."
  exit 0
fi

# Print scope and selected workloads
if [[ -z "$NAMESPACE" && "$ALL_NAMESPACES" == false ]]; then
  echo "Scope: ArgoCD Application projects: $PROJECTS"
  if [[ -n "$APP_FILTER" ]]; then
    echo "Filter: app = $APP_FILTER"
  fi
  if [[ -n "$APP_REGEX" ]]; then
    echo "Filter: app-regex = $APP_REGEX"
  fi
elif [[ -n "$NAMESPACE" ]]; then
  echo "Scope: namespace $NAMESPACE"
else
  echo "Scope: all namespaces"
fi

if [[ "$PARALLEL" -gt 1 ]]; then
  echo "Concurrency: $PARALLEL"
fi
echo
echo "Workloads selected for restart:"
column -t -s $'\t' "$TMP_WORKLOADS"
echo

TOTAL=$(wc -l < "$TMP_WORKLOADS")
echo "Total: $TOTAL workload(s)"

if [[ "$DRY_RUN" == true ]]; then
  echo
  echo "Dry run only. Re-run with --yes to restart these workload controllers."
  exit 0
fi

# ── Restart workloads ──────────────────────────────────────────────────────

START_TIME=$(date +%s)
echo
echo "Restarting selected workload controllers..."

# Function to restart a single workload and record result
restart_one() {
  local kind="$1" namespace="$2" name="$3"
  local api_kind
  api_kind="$(tr '[:upper:]' '[:lower:]' <<< "$kind")"
  if kubectl -n "$namespace" rollout restart "${api_kind}/${name}" 2>/dev/null; then
    printf 'OK\t%s\t%s\t%s\n' "$kind" "$namespace" "$name"
  else
    printf 'FAIL\t%s\t%s\t%s\n' "$kind" "$namespace" "$name"
  fi
}

if [[ "$PARALLEL" -gt 1 ]]; then
  # Parallel restarts with semaphore (background jobs)
  ACTIVE=0
  : > "$TMP_RESULTS"
  while IFS=$'\t' read -r kind namespace name; do
    (
      restart_one "$kind" "$namespace" "$name" >> "$TMP_RESULTS"
    ) &
    ACTIVE=$((ACTIVE + 1))
    if [[ "$ACTIVE" -ge "$PARALLEL" ]]; then
      # Wait for any one background job to finish (bash 3.2 compatible)
      local_pids=$(jobs -p)
      for pid in $local_pids; do
        wait "$pid" 2>/dev/null && break
      done
      ACTIVE=$((ACTIVE - 1))
    fi
  done < "$TMP_WORKLOADS"
  wait
else
  # Sequential restarts
  while IFS=$'\t' read -r kind namespace name; do
    restart_one "$kind" "$namespace" "$name"
  done < "$TMP_WORKLOADS" > "$TMP_RESULTS"
fi

RESTART_TIME=$(date +%s)

# ── Wait for rollouts ──────────────────────────────────────────────────────

if [[ "$WAIT" == true ]]; then
  echo
  echo "Waiting for rollouts to complete (timeout per workload: $TIMEOUT)..."

  DONE=0
  WAIT_OK=0
  WAIT_FAIL=0
  : > "$TMP_WAIT_FAIL"  # truncate

  while IFS=$'\t' read -r status kind namespace name; do
    [[ "$status" == "OK" ]] || continue
    DONE=$((DONE + 1))
    api_kind="$(tr '[:upper:]' '[:lower:]' <<< "$kind")"

    # Progress indicator on a single line
    printf "\r  [%d/%d] waiting %s/%s -n %s" "$DONE" "$TOTAL" "$api_kind" "$name" "$namespace"

    if kubectl -n "$namespace" rollout status "${api_kind}/${name}" --timeout="$TIMEOUT" >/dev/null 2>&1; then
      WAIT_OK=$((WAIT_OK + 1))
    else
      WAIT_FAIL=$((WAIT_FAIL + 1))
      printf "\n  FAIL: %s/%s -n %s" "$api_kind" "$name" "$namespace"
      printf '%s\t%s\t%s\n' "$kind" "$namespace" "$name" >> "$TMP_WAIT_FAIL"
    fi
  done < "$TMP_RESULTS"

  echo  # newline after progress
  WAIT_TIME=$(date +%s)
fi

# ── Summary report ─────────────────────────────────────────────────────────

END_TIME=$(date +%s)
RESTART_ELAPSED=$((RESTART_TIME - START_TIME))
TOTAL_ELAPSED=$((END_TIME - START_TIME))

# Count results
OK_COUNT=$(grep -c '^OK' "$TMP_RESULTS" || true)
FAIL_COUNT=$(grep -c '^FAIL' "$TMP_RESULTS" || true)
OK_COUNT=${OK_COUNT:-0}
FAIL_COUNT=${FAIL_COUNT:-0}

echo
echo "═══════════════════════════════════════════════════════════"
echo "  Summary"
echo "═══════════════════════════════════════════════════════════"
echo "  Total workloads:    $TOTAL"
echo "  Restarted OK:       $OK_COUNT"
echo "  Restarted FAIL:     $FAIL_COUNT"

if [[ "$WAIT" == true ]]; then
  echo "  Rollouts OK:        $WAIT_OK"
  echo "  Rollouts FAIL:      $WAIT_FAIL"
  echo "  Wait time:          $((WAIT_TIME - RESTART_TIME))s"
fi

echo "  Restart time:       ${RESTART_ELAPSED}s"
echo "  Total time:         ${TOTAL_ELAPSED}s"
echo "═══════════════════════════════════════════════════════════"

# Print failures if any
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  echo
  echo "Failed restarts:"
  grep '^FAIL' "$TMP_RESULTS" | while IFS=$'\t' read -r _ kind namespace name; do
    echo "  ✗ ${kind}/${name} -n ${namespace}"
  done
fi

if [[ "$WAIT" == true && -s "$TMP_WAIT_FAIL" ]]; then
  echo
  echo "Failed rollouts:"
  while IFS=$'\t' read -r kind namespace name; do
    api_kind="$(tr '[:upper:]' '[:lower:]' <<< "$kind")"
    echo "  ✗ ${api_kind}/${name} -n ${namespace}"
  done < "$TMP_WAIT_FAIL"
fi

if [[ "$FAIL_COUNT" -eq 0 && ( "$WAIT" == false || "$WAIT_FAIL" -eq 0 ) ]]; then
  echo
  echo "All workloads restarted successfully."
  exit 0
else
  echo
  echo "Some workloads failed. Check the output above."
  exit 1
fi