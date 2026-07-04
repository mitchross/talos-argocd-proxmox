#!/usr/bin/env bash
# PreToolUse guard for Bash git commands (global rule, 2026-07-04):
#   - NEVER commit or push while on main/master, and never push TO main/master
#     explicitly (e.g. `git push origin main`, `... HEAD:main`).
#   - On any other branch, commit/push are auto-allowed (no permission prompt) --
#     PR-branch workflow is the paved road.
# Emits a PreToolUse permissionDecision; emits nothing (normal permission flow)
# for commands it has no opinion on (non-commit/push git, detached HEAD).
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

# Explicit push target main/master anywhere in the command -- deny regardless
# of the current branch (covers `git push origin main`, `-u origin master`,
# `HEAD:main`, `refs/heads/main`).
if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push[^;&|]*([[:space:]]|:|refs/heads/)(main|master)([[:space:]]|$)'; then
  deny "Global rule: never push to main/master. Push to a feature/PR branch and open a PR instead."
fi

# Branch the command will run on.
branch=$(git -C "$cwd" symbolic-ref --short -q HEAD 2>/dev/null || true)
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
