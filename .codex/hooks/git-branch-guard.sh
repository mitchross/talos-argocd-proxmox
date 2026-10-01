#!/usr/bin/env bash
# Both clients use the same deny-only policy; preserve the JSON payload on stdin.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
exec python3 "$repo_root/scripts/agent-git-guard.py"
