#!/bin/sh
# Copy config from ConfigMap to PVC (HA needs writable config files)
cp /config-source/configuration.yaml /config/configuration.yaml
cp /config-source/automations.yaml /config/automations.yaml
cp /config-source/scripts.yaml /config/scripts.yaml
cp /config-source/scenes.yaml /config/scenes.yaml
cp /config-source/customize.yaml /config/customize.yaml
cp /config-source/lovelace-homelab-power.yaml /config/lovelace-homelab-power.yaml
# Ensure themes directory exists
mkdir -p /config/themes
# AirCube ZHA quirk -> custom_zha_quirks/ (loaded via zha.custom_quirks_path)
mkdir -p /config/custom_zha_quirks
cp /config-source/aircube.py /config/custom_zha_quirks/aircube.py
echo "Config files copied to PVC"

