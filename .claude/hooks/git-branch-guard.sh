#!/usr/bin/env bash
# Guard commits and pushes on main/master, including explicit push targets.
# Emit a PreToolUse decision; unrelated commands and detached HEAD use normal permissions.
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
cwd=$(printf '%s' "$input" | jq -r '.cwd // "."')

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"
  exit 0
}
allow() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"%s"}}\n' "$1"
  exit 0
}

# Only weigh in on git commit / git push invocations.
if ! printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+(commit|push)([[:space:]]|$)'; then
  exit 0
fi

# Reject explicit main/master push targets regardless of the current branch.
if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push[^;&|]*([[:space:]]|:|refs/heads/)(main|master)([[:space:]]|$)'; then
  deny "Global rule: never push to main/master. Push to a feature/PR branch and open a PR instead."
fi

# Honor git -C so worktree commands are checked against their target checkout.
target=$(printf '%s' "$cmd" | sed -nE 's|.*[[:space:]]-C[[:space:]]+([^[:space:]]+).*|\1|p' | head -1)
[ -n "$target" ] || target="$cwd"
branch=$(git -C "$target" symbolic-ref --short -q HEAD 2>/dev/null || true)
case "$branch" in
  main|master)
    deny "Global rule: currently on $branch -- no commit/push on main/master. Create a feature branch first (git checkout -b <branch>)."
    ;;
  "")
    # Detached HEAD or not a repo: no opinion, fall through to normal permissions.
    exit 0
    ;;
  *)
    allow "On feature branch $branch: commit/push allowed by global branch rule."
    ;;
esac
