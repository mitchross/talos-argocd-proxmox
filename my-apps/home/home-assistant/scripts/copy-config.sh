#!/bin/sh
set -eu

# Copy config from ConfigMap to PVC (HA needs writable config files)
cp /config-source/configuration.yaml /config/configuration.yaml
cp /config-source/automations.yaml /config/automations.yaml
cp /config-source/scripts.yaml /config/scripts.yaml
cp /config-source/scenes.yaml /config/scenes.yaml
cp /config-source/customize.yaml /config/customize.yaml
cp /config-source/lovelace-homelab-power.yaml /config/lovelace-homelab-power.yaml
cp /config-source/power-insights.yaml /config/power-insights.yaml
# Ensure themes directory exists
mkdir -p /config/themes
# AirCube ZHA quirk -> custom_zha_quirks/ (loaded via zha.custom_quirks_path)
mkdir -p /config/custom_zha_quirks
cp /config-source/aircube.py /config/custom_zha_quirks/aircube.py
mkdir -p /config/custom_components/consumers_energy_restore
cp /opt/repo-scripts/consumers-energy-restore.py /config/custom_components/consumers_energy_restore/__init__.py
cp /opt/repo-scripts/consumers-energy-snapshot.py /config/custom_components/consumers_energy_restore/snapshot.py
cp /opt/repo-scripts/consumers-energy-manifest.json /config/custom_components/consumers_energy_restore/manifest.json
echo "Config files copied to PVC"

