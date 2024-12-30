#!/bin/bash

# Base directory for all Kubernetes storage
BASE_DIR="/datapool/kubernetes"

# Array of directories to create
DIRS=(
    # AI applications
    "ollama-models"
    "ollama-webui"
    "comfyui/data"
    
    # Media applications
    "jellyfin/config"
    "plex/config"
    "plex/transcode"
    "homepage-dashboard"
    "reubah"
    
    # Home automation
    "frigate/config"
    "frigate/media"
    "frigate/mqtt"
    
    # Privacy applications
    "proxitok/cache"
    "searxng/config"
    
    # Monitoring
    "monitoring/prometheus"
    "monitoring/loki"
)

echo "Creating storage directories under $BASE_DIR"

# Create base directory if it doesn't exist
sudo mkdir -p "$BASE_DIR"

# Create each directory
for dir in "${DIRS[@]}"; do
    full_path="$BASE_DIR/$dir"
    echo "Creating $full_path"
    sudo mkdir -p "$full_path"
done

# Set permissions (adjust user/group as needed)
echo "Setting permissions"
sudo chown -R 1000:1000 "$BASE_DIR"
sudo chmod -R 755 "$BASE_DIR"

echo "Storage directories created successfully" 