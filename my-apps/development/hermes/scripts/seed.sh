#!/bin/sh
# Init container, runs as root before s6 starts: apply the Git-owned config, skill and cron job; install plugins once.
set -eu
HERMES_HOME=/opt/data
export HERMES_HOME PATH="/command:${PATH}"
mkdir -p "$HERMES_HOME/workspace" "$HERMES_HOME/skills/devops/homelab-ops" "$HERMES_HOME/.local/bin"
install -o 10000 -g 10000 -m 0644 /etc/hermes-config/config.yaml "$HERMES_HOME/config.yaml"
install -o 10000 -g 10000 -m 0644 /etc/hermes-skills/SKILL.md "$HERMES_HOME/skills/devops/homelab-ops/SKILL.md"
chown 10000:10000 "$HERMES_HOME" "$HERMES_HOME/workspace" "$HERMES_HOME/skills" "$HERMES_HOME/skills/devops" "$HERMES_HOME/skills/devops/homelab-ops" "$HERMES_HOME/.local" "$HERMES_HOME/.local/bin"
for plugin in hindsight homeassistant; do
  if [ ! -d "$HERMES_HOME/plugins/$plugin" ]; then
    echo "[seed] installing plugin $plugin"
    s6-setuidgid hermes /opt/hermes/bin/hermes plugins install "$plugin" --enable --yes-deps
  fi
done
if ! grep -qs '"homelab-digest"' "$HERMES_HOME/cron/jobs.json"; then
  echo "[seed] creating cron job homelab-digest"
  s6-setuidgid hermes /opt/hermes/bin/hermes cron create "every day at 08:00" \
    "Load the homelab-ops skill, run all six checks, and write the digest in the skill's format." \
    --skill homelab-ops --name homelab-digest
fi
echo "[seed] done"
