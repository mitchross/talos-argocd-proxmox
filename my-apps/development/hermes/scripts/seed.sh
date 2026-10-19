#!/bin/sh
# Init container, runs as root before s6 starts: apply the Git-owned config and install plugins once.
set -eu
HERMES_HOME=/opt/data
export HERMES_HOME PATH="/command:${PATH}"
mkdir -p "$HERMES_HOME/workspace"
install -o 10000 -g 10000 -m 0644 /etc/hermes-config/config.yaml "$HERMES_HOME/config.yaml"
chown 10000:10000 "$HERMES_HOME" "$HERMES_HOME/workspace"
for plugin in hindsight langfuse homeassistant; do
  if [ ! -d "$HERMES_HOME/plugins/$plugin" ]; then
    echo "[seed] installing plugin $plugin"
    s6-setuidgid hermes /opt/hermes/bin/hermes plugins install "$plugin" --enable --yes-deps
  fi
done
echo "[seed] done"
