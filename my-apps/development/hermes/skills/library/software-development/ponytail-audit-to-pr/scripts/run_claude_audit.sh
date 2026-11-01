#!/usr/bin/env bash
# Run read-only Claude Code auditors in parallel, one per area, each on a pinned model.
# Usage: run_claude_audit.sh <brief-dir> <PREFIX>:<model> [<PREFIX>:<model> ...]
# Needs <brief-dir>/brief-<PREFIX>.md (full brief: repo path + SHA, scope, load, rules, output shape).
# Writes <brief-dir>/audit-<PREFIX>.md (the report) and .json/.err. Run from anywhere; cwd is the repo
# named in REPO (default: current dir). Tools are Read/Glob/Grep only, so nothing can be changed.
set -u
D=$1; shift
REPO=${REPO:-$PWD}
run_one() {
  local P=${1%%:*} M=${1#*:}
  ( cd "$REPO" && claude -p "$(cat "$D/brief-$P.md")" --model "$M" --effort high --max-turns 150 \
      --allowedTools "Read,Glob,Grep" --disallowedTools "Edit,Write,Bash" \
      --output-format json > "$D/audit-$P.json" 2> "$D/audit-$P.err" )
  echo "$P ($M) EXIT=$?"
  /opt/hermes/.venv/bin/python - "$D/audit-$P.json" "$D/audit-$P.md" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("no result JSON:", e); sys.exit(0)
open(sys.argv[2], "w").write(d.get("result", ""))
print(d.get("subtype"), "turns", d.get("num_turns"), "cost", d.get("total_cost_usd"))
PY
}
for spec in "$@"; do run_one "$spec" & done
wait
ls -la "$D"/audit-*.md
