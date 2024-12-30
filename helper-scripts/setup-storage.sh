#!/bin/bash

# Base directory
BASE_DIR="/datapool/kubernetes"

# Array of directories to create
declare -a DIRS=(
    # AI Services
    "ollama-models"
    "comfyui/data"
    
    # Media Services
    "jellyfin/config"
    "frigate/config"
    "frigate/media"
    
    # *arr Services
    "arr/sonarr/config"
    "arr/radarr/config"
    "arr/lidarr/config"
    "arr/prowlarr/config"
    
    # Privacy Services
    "proxitok/cache"
    "searxng/config"
)

# Create base directory if it doesn't exist
echo "Creating base directory: $BASE_DIR"
sudo mkdir -p "$BASE_DIR"

# Create each directory and set permissions
for dir in "${DIRS[@]}"; do
    FULL_PATH="$BASE_DIR/$dir"
    echo "Creating directory: $FULL_PATH"
    sudo mkdir -p "$FULL_PATH"
    sudo chown -R 1000:1000 "$FULL_PATH"
    sudo chmod -R 755 "$FULL_PATH"
done

echo "Storage directories created successfully!"
echo "Base path: $BASE_DIR"
echo "Created directories:"
for dir in "${DIRS[@]}"; do
    echo "- $dir"
done 