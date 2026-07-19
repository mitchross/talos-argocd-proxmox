#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${repo_root}/docs/diagrams"
committed_dir="${repo_root}/docs/assets"
temporary_dir="$(mktemp -d)"
config="${source_dir}/mermaid-config.json"
puppeteer_config="${source_dir}/puppeteer-config.json"
shared_hash_inputs=(
  "${config}"
  "${puppeteer_config}"
  "${repo_root}/package-lock.json"
  "${repo_root}/scripts/render-diagrams.sh"
  "${repo_root}/scripts/normalize-diagram.mjs"
  "${repo_root}/scripts/diagram-hash.mjs"
)

trap 'rm -rf "${temporary_dir}"' EXIT

DIAGRAM_OUTPUT_DIR="${temporary_dir}" \
  bash "${repo_root}/scripts/render-diagrams.sh"

for source in "${source_dir}"/*.mmd; do
  name="$(basename "${source}" .mmd)"
  hash_inputs=("${source}" "${shared_hash_inputs[@]}")

  node "${repo_root}/scripts/verify-diagram.mjs" \
    "${committed_dir}/${name}.svg" \
    "${hash_inputs[@]}"
  node "${repo_root}/scripts/verify-diagram.mjs" \
    "${temporary_dir}/${name}.svg" \
    "${hash_inputs[@]}"
done
