#!/usr/bin/env bash
# Shared helpers for scripts/dr/*
# shellcheck shell=bash

# ---------- colors / logging ------------------------------------------------
if [[ -t 1 ]]; then
  RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; BLU=$'\033[34m'; DIM=$'\033[2m'; RST=$'\033[0m'
else
  RED= YEL= GRN= BLU= DIM= RST=
fi

log()  { printf "%s[%s]%s %s\n"  "$BLU" "$(date +%H:%M:%S)" "$RST" "$*" >&2; }
warn() { printf "%s[WARN]%s %s\n" "$YEL" "$RST" "$*" >&2; }
die()  { printf "%s[ERR]%s %s\n"  "$RED" "$RST" "$*" >&2; exit 1; }
ok()   { printf "%s✓%s %s\n"     "$GRN" "$RST" "$*" >&2; }
step() { printf "\n%s━━ %s ━━%s\n" "$BLU" "$*" "$RST" >&2; }

# ---------- preflight -------------------------------------------------------
check_deps() {
  local missing=()
  for cmd in yq kubectl jq; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if (( ${#missing[@]} > 0 )); then
    die "missing required tools: ${missing[*]} (install: sudo pacman -S yq kubectl jq)"
  fi
  # yq must be mikefarah/yq (Go). Python version is incompatible.
  if ! yq --version 2>&1 | grep -q "mikefarah"; then
    warn "yq doesn't look like mikefarah/yq — scripts may not work. Install: sudo pacman -S yq"
  fi
}

# ---------- repo paths ------------------------------------------------------
repo_root() {
  git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel
}

db_dir() {
  local db="$1"
  echo "$(repo_root)/infrastructure/database/cloudnative-pg/$db"
}

lineage_path() {
  echo "$(db_dir "$1")/lineage.yaml"
}

cluster_yaml_path() {
  echo "$(db_dir "$1")/cluster.yaml"
}

# ---------- lineage accessors (require mikefarah/yq) ------------------------
lineage_get() {
  local db="$1" field="$2"
  yq -r ".$field" "$(lineage_path "$db")"
}

# Compute the next serverName in a -v<N> sequence. 'foo-v3' -> 'foo-v4'.
# Unversioned names ('foo') -> 'foo-v2'.
next_serverName() {
  local cur="$1"
  if [[ "$cur" =~ ^(.+)-v([0-9]+)$ ]]; then
    printf "%s-v%d\n" "${BASH_REMATCH[1]}" "$((BASH_REMATCH[2] + 1))"
  else
    printf "%s-v2\n" "$cur"
  fi
}

# ---------- ArgoCD helpers --------------------------------------------------
# Find the ArgoCD Application(s) that manage this DB. Returns names on stdout,
# one per line. Both the CNPG Cluster app (name = db) AND any consumer
# my-apps-* app.
argocd_apps_for_db() {
  local db="$1"
  kubectl -n argocd get applications --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null \
    | awk -v db="$db" '$1 == db || $1 == "my-apps-" db { print $1 }'
}

argocd_pause() {
  local app="$1"
  kubectl -n argocd annotate application "$app" \
    argocd.argoproj.io/skip-reconcile=true --overwrite >/dev/null 2>&1 \
    || warn "could not annotate $app (may not exist)"
}

argocd_unpause() {
  local app="$1"
  kubectl -n argocd annotate application "$app" \
    argocd.argoproj.io/skip-reconcile- --overwrite >/dev/null 2>&1 \
    || warn "could not remove annotation on $app"
}
