#!/usr/bin/env bash
# Run the CI gates of an npm + Python repo (deal-scout layout) one at a time; each to <logdir>/<name>.log.
# Usage: run_npm_py_gates.sh <worktree> <logdir> [env-file]
# Prints one exit line per gate, then the node/worker pass-fail counts and the pytest summary.
set -u
WT=$1; LOG=$2; ENVF=${3:-/opt/data/tools/deal-scout-env.sh}
mkdir -p "$LOG"
[ -f "$ENVF" ] && source "$ENVF"
cd "$WT" || exit 1
[ -d node_modules ] || npm ci --no-audit --no-fund > "$LOG/npm-ci-root.log" 2>&1
[ -d worker/node_modules ] || (cd worker && npm ci --no-audit --no-fund) > "$LOG/npm-ci-worker.log" 2>&1
run() { name=$1; shift; "$@" > "$LOG/$name.log" 2>&1; echo "$name exit=$?"; }
run ruff ruff check .
run eslint npx eslint .
run dryrun node scraper/scrape.mjs --sites __none__ --dry-run
run node-tests node --test --test-concurrency=4 scraper/*.test.mjs dashboard/static/*.test.cjs
run worker-test bash -c "cd worker && npm test"
run worker-typecheck bash -c "cd worker && npm run typecheck"
run pytest python -m pytest -q -p no:cacheprovider dashboard
grep -h -E "^ℹ (pass|fail) " "$LOG/node-tests.log" "$LOG/worker-test.log" | paste -sd' '
tail -1 "$LOG/pytest.log"
echo "node $(node -v) / $(python --version)"
