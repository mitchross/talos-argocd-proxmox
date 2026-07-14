#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${repo_root}/docs/diagrams"
output_dir="${repo_root}/docs/assets"
config="${source_dir}/mermaid-config.json"
puppeteer_config="${source_dir}/puppeteer-config.json"

for source in "${source_dir}"/*.mmd; do
  name="$(basename "${source}" .mmd)"
  npx mmdc \
    --quiet \
    --input "${source}" \
    --output "${output_dir}/${name}.svg" \
    --configFile "${config}" \
    --puppeteerConfigFile "${puppeteer_config}" \
    --backgroundColor white
  node "${repo_root}/scripts/normalize-diagram.mjs" "${output_dir}/${name}.svg"
done
