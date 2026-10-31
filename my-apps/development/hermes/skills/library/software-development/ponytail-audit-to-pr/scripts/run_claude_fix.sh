#!/usr/bin/env bash
# Run Claude Code (print mode) on a fix prompt inside a worktree; env reaches its Bash via --settings.
# Usage: [EXTRA_TOOLS="Bash(curl *),Bash(python3 *)"] run_claude_fix.sh <worktree> <prompt.md> [model] [env-file]
# Output: $SCRATCH/claude-fix-<worktree name>.json (result) and .err, one pair per worktree so parallel runs don't clobber each other. Never merges.
# Don't run two of these on the same worktree at once: both write the same .json (stop the first by PID, not pkill -f).
set -u
WT=$1; PROMPT=$2; MODEL=${3:-claude-sonnet-5-5}; ENVF=${4:-}
SCRATCH=${TMPDIR:-/opt/data/cache/scratch}
OUT="$SCRATCH/claude-fix-$(basename "$WT")"
[ -n "$ENVF" ] && source "$ENVF"
cd "$WT" || exit 1
SETTINGS=$(/opt/hermes/.venv/bin/python -c '
import json, os
keys = ["PATH", "RUSTUP_HOME", "CARGO_HOME", "RUSTUP_TOOLCHAIN", "PROTOC", "PROTOC_INCLUDE", "LIBCLANG_PATH", "BINDGEN_EXTRA_CLANG_ARGS", "CARGO_TARGET_DIR"]
print(json.dumps({"env": {k: os.environ[k] for k in keys if k in os.environ}}))')
claude -p "$(cat "$PROMPT")" \
  --model "$MODEL" --effort high --max-turns 200 \
  --permission-mode acceptEdits --add-dir "$SCRATCH" --settings "$SETTINGS" \
  --allowedTools "Read,Edit,Write,Glob,Grep,Bash(cargo *),Bash(bun *),Bash(bunx *),Bash(git *),Bash(gh issue view *),Bash(gh pr create *),Bash(gh pr view *),Bash(gh pr edit *),Bash(cd *),Bash(ls *),Bash(cat *),Bash(grep *),Bash(rg *),Bash(head *),Bash(tail *),Bash(sleep *),Bash(timeout *)${EXTRA_TOOLS:+,$EXTRA_TOOLS}" \
  --disallowedTools "Bash(gh pr merge *),Bash(git push origin master*),Bash(git push origin main*),Bash(git push * master*),Bash(git push * main*),Bash(git push --force*)" \
  --output-format json > "$OUT.json" 2> "$OUT.err"
echo "EXIT=$?"
# Print the last complete JSON object: a killed earlier run can leave extra data in the same file.
/opt/hermes/.venv/bin/python - "$OUT.json" <<'PY'
import json, sys
s = open(sys.argv[1], errors="replace").read()
dec, i, last = json.JSONDecoder(), 0, None
while i < len(s):
    j = s.find("{", i)
    if j < 0: break
    try:
        last, i = dec.raw_decode(s, j)
    except ValueError:
        i = j + 1
if not last:
    print("no result JSON; check git log / gh pr view for the branch"); sys.exit(0)
print(last.get("subtype"), last.get("num_turns"), last.get("total_cost_usd"))
print(str(last.get("result", ""))[-3000:])
PY
