#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${repo_root}/docs/diagrams"
output_dir="${DIAGRAM_OUTPUT_DIR:-${repo_root}/docs/assets}"
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

mkdir -p "${output_dir}"

for source in "${source_dir}"/*.mmd; do
  name="$(basename "${source}" .mmd)"
  npx mmdc \
    --quiet \
    --input "${source}" \
    --output "${output_dir}/${name}.svg" \
    --configFile "${config}" \
    --puppeteerConfigFile "${puppeteer_config}" \
    --backgroundColor white
  node "${repo_root}/scripts/normalize-diagram.mjs" \
    "${output_dir}/${name}.svg" \
    "${source}" \
    "${shared_hash_inputs[@]}"
done
