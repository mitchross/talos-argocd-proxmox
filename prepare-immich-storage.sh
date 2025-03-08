#!/bin/bash

# Set the base directory
BASE_DIR="/datapool/kubernetes/immich-data"

# Create the base directory if it doesn't exist
mkdir -p "$BASE_DIR"

# Create the required subdirectories
mkdir -p "$BASE_DIR/encoded-video"
mkdir -p "$BASE_DIR/library"
mkdir -p "$BASE_DIR/ml-cache"
mkdir -p "$BASE_DIR/profile"
mkdir -p "$BASE_DIR/thumbs"
mkdir -p "$BASE_DIR/upload"

# Set permissions
chmod -R 775 "$BASE_DIR"

echo "Immich directory structure has been prepared at $BASE_DIR"
echo "The following directories have been created:"
ls -la "$BASE_DIR"

echo ""
echo "Now you can apply your Kubernetes manifests to deploy Immich." 