#!/bin/sh
# Init container, runs as root before s6 starts: apply the Git-owned config, skill and cron job; install plugins and hooks once.
set -eu
HERMES_HOME=/opt/data
HOME=/opt/data
REPO_URL=https://github.com/mitchross/talos-argocd-proxmox.git
REPO_DIR="$HERMES_HOME/workspace/talos-argocd-proxmox"
export HERMES_HOME HOME PATH="/command:${PATH}"
as_hermes() { s6-setuidgid hermes env HOME="$HOME" "$@"; }

mkdir -p "$HERMES_HOME/workspace" "$HERMES_HOME/skills/devops/homelab-ops" "$HERMES_HOME/.local/bin" "$HERMES_HOME/.hindsight"
install -o 10000 -g 10000 -m 0644 /etc/hermes-config/config.yaml "$HERMES_HOME/config.yaml"
install -o 10000 -g 10000 -m 0644 /etc/hermes-skills/SKILL.md "$HERMES_HOME/skills/devops/homelab-ops/SKILL.md"
# Hook configs for claude and codex in this pod; the token comes from the mounted Secret, never from Git.
for f in claude-code codex; do
  sed "s|__HINDSIGHT_API_KEY__|${HINDSIGHT_API_KEY}|" "/etc/hermes-config/hindsight-$f.json" > "$HERMES_HOME/.hindsight/$f.json"
  chown 10000:10000 "$HERMES_HOME/.hindsight/$f.json"; chmod 0600 "$HERMES_HOME/.hindsight/$f.json"
done
chown 10000:10000 "$HERMES_HOME" "$HERMES_HOME/workspace" "$HERMES_HOME/skills" "$HERMES_HOME/skills/devops" "$HERMES_HOME/skills/devops/homelab-ops" "$HERMES_HOME/.local" "$HERMES_HOME/.local/bin" "$HERMES_HOME/.hindsight"

for plugin in hindsight homeassistant; do
  if [ ! -d "$HERMES_HOME/plugins/$plugin" ]; then
    echo "[seed] installing plugin $plugin"
    as_hermes /opt/hermes/bin/hermes plugins install "$plugin" --enable --yes-deps
  fi
done
if ! grep -qs '"homelab-digest"' "$HERMES_HOME/cron/jobs.json"; then
  echo "[seed] creating cron job homelab-digest"
  as_hermes /opt/hermes/bin/hermes cron create "every day at 08:00" \
    "Load the homelab-ops skill, run all six checks, and write the digest in the skill's format." \
    --skill homelab-ops --name homelab-digest
fi

# Coding agents: repo checkout, git identity, shared-memory hooks. gh and codex logins are done once by hand (docs).
as_hermes git config --global user.name "Hermes Agent"
as_hermes git config --global user.email "mitchross@users.noreply.github.com"
as_hermes git config --global init.defaultBranch main
if [ ! -d "$REPO_DIR/.git" ]; then
  echo "[seed] cloning talos-argocd-proxmox"
  as_hermes git clone --quiet "$REPO_URL" "$REPO_DIR" || echo "[seed] clone failed, continuing"
else
  as_hermes git -C "$REPO_DIR" fetch --quiet --prune origin || echo "[seed] fetch failed, continuing"
fi
if as_hermes gh auth status >/dev/null 2>&1; then
  as_hermes gh auth setup-git >/dev/null 2>&1 || true
fi
if ! grep -qs hindsight-memory "$HERMES_HOME/.claude/plugins/installed_plugins.json"; then
  echo "[seed] installing Claude Code plugin hindsight-memory"
  as_hermes claude plugin marketplace add vectorize-io/hindsight >/dev/null 2>&1 || true
  as_hermes claude plugin install hindsight-memory || echo "[seed] claude plugin install failed, continuing"
fi
if [ ! -f "$HERMES_HOME/.codex/hooks.json" ]; then
  echo "[seed] installing Codex Hindsight hooks"
  # --mode local only writes hooks; cloud mode would overwrite .hindsight/codex.json.
  as_hermes sh -c 'curl -fsSL https://hindsight.vectorize.io/get-codex | bash -s -- --mode local' || echo "[seed] codex hooks install failed, continuing"
fi
echo "[seed] done"
