#!/bin/sh
# Downloads the pinned AI Assistant plugin, verifies its SHA256 and unpacks it into the plugins dir.
set -eu
wget -qO /tmp/ai.tgz "https://github.com/headlamp-k8s/plugins/releases/download/ai-assistant-${PLUGIN_VERSION}/headlamp-k8s-ai-assistant-${PLUGIN_VERSION}.tar.gz"
echo "${PLUGIN_SHA256}  /tmp/ai.tgz" | sha256sum -c -
tar xzf /tmp/ai.tgz -C /headlamp/plugins
