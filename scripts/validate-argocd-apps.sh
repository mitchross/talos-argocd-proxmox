#!/usr/bin/env bash
# validate-argocd-apps.sh — local ArgoCD app-of-apps validation.
#
# Run from repo root:
#   ./scripts/validate-argocd-apps.sh          # validates talos and openshift
#   ./scripts/validate-argocd-apps.sh talos
#   ./scripts/validate-argocd-apps.sh openshift

set -euo pipefail

ERRORS=0

clusters=("$@")
if [ ${#clusters[@]} -eq 0 ]; then
  clusters=(talos openshift)
fi

fail() {
  echo "  ERROR: $*"
  ERRORS=$((ERRORS + 1))
}

yaml_kind_files() {
  local apps_dir="$1"
  find "$apps_dir" -type f \( -name "*.yaml" -o -name "*.yml" \) | sort
}

application_files() {
  local apps_dir="$1"
  yaml_kind_files "$apps_dir" | while IFS= read -r f; do
    grep -q "^kind: Application$" "$f" 2>/dev/null && printf '%s\n' "$f"
  done
}

metadata_files() {
  local cluster="$1"
  find "clusters/$cluster" -path "*/.argocd/config.json" -type f \
    ! -path "clusters/$cluster/apps/*/*/.argocd/config.json" | sort
}

app_overlay_dirs() {
  local cluster="$1"
  find "clusters/$cluster/apps" -mindepth 3 -maxdepth 3 \
    -type f -name kustomization.yaml -printf '%h\n' | sort
}

derived_app_name() {
  local cluster="$1"
  local dir="$2"
  local relative="${dir#clusters/$cluster/apps/}"
  local category="${relative%%/*}"
  local app="${relative#*/}"
  printf '%s-apps-%s-%s\n' "$cluster" "$category" "$app"
}

json_field() {
  local file="$1"
  local field="$2"
  python3 - "$file" "$field" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
print(data.get(sys.argv[2], ""))
PY
}

standalone_name() {
  sed -n '/^metadata:/,/^spec:/p' "$1" | sed -n 's/^  name: *//p' | head -1 | tr -d "'\""
}

standalone_path() {
  sed -n '/^  source:/,/^  destination:/p' "$1" | sed -n 's/^    path: *//p' | head -1 | tr -d "'\""
}

validate_cluster() {
  local cluster="$1"
  local apps_dir="clusters/$cluster/argocd"
  local bootstrap_dir="clusters/$cluster/bootstrap"
  local self_managed_dir="clusters/$cluster/infra/argocd"

  echo "=== ArgoCD Application Validation: $cluster ==="
  echo ""

  if [ ! -d "$apps_dir" ]; then
    fail "missing $apps_dir"
    echo ""
    return
  fi

  echo "--- Check 0: App overlay count ---"
  app_count="$(app_overlay_dirs "$cluster" | wc -l | xargs)"
  if [ "$app_count" -ne 44 ]; then
    fail "expected 44 $cluster app overlays, found $app_count"
  else
    echo "  OK: Found 44 app overlays"
  fi
  echo ""

  echo "--- Check 1: Duplicate Application names ---"
  declare -A seen=()

  while IFS= read -r f; do
    name="$(standalone_name "$f")"
    [ -n "$name" ] || continue
    if [ -n "${seen[$name]:-}" ]; then
      fail "'$name' appears in both ${seen[$name]} and $f"
    else
      seen[$name]="$f"
    fi
  done < <(application_files "$apps_dir")

  while IFS= read -r f; do
    name="$(json_field "$f" applicationName)"
    [ -n "$name" ] || fail "$f missing applicationName"
    if [ -n "${seen[$name]:-}" ]; then
      fail "'$name' appears in both ${seen[$name]} and $f"
    else
      seen[$name]="$f"
    fi
  done < <(metadata_files "$cluster")

  while IFS= read -r dir; do
    name="$(derived_app_name "$cluster" "$dir")"
    if [ -n "${seen[$name]:-}" ]; then
      fail "'$name' appears in both ${seen[$name]} and $dir"
    else
      seen[$name]="$dir"
    fi
  done < <(app_overlay_dirs "$cluster")

  [ $ERRORS -eq 0 ] && echo "  OK: No duplicate Application names found"
  echo ""

  echo "--- Check 2: Sync wave continuity ---"
  waves=()
  while IFS= read -r f; do
    wave="$(grep "sync-wave:" "$f" 2>/dev/null | head -1 | sed 's/.*sync-wave: *//' | tr -d '"' | xargs || true)"
    [ -n "$wave" ] && waves+=("$wave")
  done < <(yaml_kind_files "$apps_dir")
  while IFS= read -r f; do
    wave="$(json_field "$f" syncWave)"
    [ -n "$wave" ] && waves+=("$wave")
  done < <(metadata_files "$cluster")
  while IFS= read -r dir; do
    [ -n "$dir" ] && waves+=("6")
  done < <(app_overlay_dirs "$cluster")

  if [ ${#waves[@]} -gt 0 ]; then
    mapfile -t sorted_waves < <(printf '%s\n' "${waves[@]}" | sort -n | uniq)
    echo "  Waves found: ${sorted_waves[*]}"
  else
    fail "no sync waves found"
  fi
  echo ""

  echo "--- Check 3: kustomization.yaml lists Argo entrypoint files ---"
  local kustomization="$apps_dir/kustomization.yaml"
  if [ ! -f "$kustomization" ]; then
    fail "missing $kustomization"
  else
    while IFS= read -r f; do
      relpath="${f#"$apps_dir"/}"
      [ "$relpath" = "kustomization.yaml" ] && continue
      grep -q "kind: Application\|kind: ApplicationSet\|kind: AppProject" "$f" 2>/dev/null || continue
      if ! grep -q -- "$relpath" "$kustomization" 2>/dev/null; then
        fail "$relpath exists but is not listed in $kustomization"
      fi
    done < <(yaml_kind_files "$apps_dir")
  fi
  echo ""

  echo "--- Check 4: Source paths exist ---"
  while IFS= read -r f; do
    path="$(standalone_path "$f")"
    [ -z "$path" ] && continue
    if [ ! -f "$path/kustomization.yaml" ]; then
      fail "$f points at '$path' but no kustomization.yaml exists there"
    fi
  done < <(application_files "$apps_dir")

  while IFS= read -r f; do
    path="$(json_field "$f" sourcePath)"
    if [ -z "$path" ]; then
      fail "$f missing sourcePath"
    elif [ ! -f "$path/kustomization.yaml" ]; then
      fail "$f sourcePath '$path' has no kustomization.yaml"
    fi
  done < <(metadata_files "$cluster")
  while IFS= read -r dir; do
    if [ ! -f "$dir/kustomization.yaml" ]; then
      fail "derived app sourcePath '$dir' has no kustomization.yaml"
    fi
  done < <(app_overlay_dirs "$cluster")
  echo ""

  echo "--- Check 5: ArgoCD chart version alignment ---"
  script_version="$(grep 'ARGOCD_CHART_VERSION=' scripts/bootstrap-argocd.sh | head -1 | cut -d= -f2 | tr -d '"')"
  bootstrap_version="$(grep -A5 'name: argo-cd' "$bootstrap_dir/kustomization.yaml" | sed -n 's/.*version: *//p' | head -1 | sed 's/#.*//' | tr -d '"' | xargs)"
  self_version="$(grep -A5 'name: argo-cd' "$self_managed_dir/kustomization.yaml" | sed -n 's/.*version: *//p' | head -1 | sed 's/#.*//' | tr -d '"' | xargs)"
  if [ -z "$script_version" ] || [ "$script_version" != "$bootstrap_version" ] || [ "$script_version" != "$self_version" ]; then
    fail "$cluster ArgoCD chart versions differ: script=$script_version bootstrap=$bootstrap_version self-managed=$self_version"
  else
    echo "  OK: script, bootstrap, and self-managed chart versions match ($script_version)"
  fi
  echo ""

  if [ "$cluster" = "talos" ]; then
    echo "--- Check 6: Project Nomad remains one bundled app ---"
    project_nomad_path="clusters/talos/apps/home/project-nomad"
    if [ ! -f "$project_nomad_path/kustomization.yaml" ]; then
      fail "missing $project_nomad_path/kustomization.yaml"
    else
      nested_nomad_kustomizations=$(find "$project_nomad_path" -mindepth 2 -name kustomization.yaml -print | wc -l | xargs)
      if [ "$nested_nomad_kustomizations" -gt 0 ]; then
        fail "Project Nomad has nested kustomization.yaml files; it should remain one bundled app"
      else
        echo "  OK: Project Nomad is managed as one bundled Application"
      fi
    fi
    echo ""
  fi
}

echo "=== ArgoCD Application Validation ==="
echo ""

for cluster in "${clusters[@]}"; do
  validate_cluster "$cluster"
done

echo "=== Summary ==="
if [ $ERRORS -gt 0 ]; then
  echo "  FAILED: $ERRORS error(s) found"
  exit 1
else
  echo "  PASSED: All checks passed"
  exit 0
fi
