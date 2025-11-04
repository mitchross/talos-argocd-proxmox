#!/bin/zsh
# generate-cluster-template.sh - Generate Omni cluster template with hostnames and patches
#
# This reads machines.yaml and creates a complete cluster template with:
# - Friendly hostnames for all nodes
# - Control plane specific patches
# - GPU worker patches (NVIDIA runtime)
# - Regular worker patches (Longhorn storage)

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLUSTER_NAME="talos-proxmox"
OUTPUT_FILE="$SCRIPT_DIR/cluster-template.yaml"

print -P "%F{blue}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%f"
print -P "%F{blue}  Generating Cluster Template with Hostnames%f"
print -P "%F{blue}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%f"
echo ""

# Check for yq
if ! command -v yq &>/dev/null; then
    print -P "%F{red}Error: yq is required but not installed%f"
    echo "Install with: brew install yq"
    exit 1
fi

# Export current cluster template
print -P "%F{yellow}Exporting current cluster template...%f"
if ! omnictl cluster template export -c "$CLUSTER_NAME" -o "$OUTPUT_FILE" 2>&1; then
    print -P "%F{red}Error: Failed to export cluster template%f"
    echo "Make sure cluster '$CLUSTER_NAME' exists in Omni"
    exit 1
fi

print -P "%F{green}✓%f Exported base template"
echo ""

# Collect machine UUIDs for ControlPlane and Workers sections
CONTROL_PLANE_UUIDS=()
WORKER_UUIDS=()

# Collect control plane UUIDs
yq eval '.control_plane[]' "$SCRIPT_DIR/machines.yaml" -o json | jq -c '.' | while read -r machine; do
    uuid=$(echo "$machine" | jq -r '.uuid')
    if [[ "$uuid" != *"REPLACE"* ]]; then
        echo "$uuid"
    fi
done > /tmp/control_plane_uuids.txt

# Collect worker UUIDs (both GPU and regular)
yq eval '.gpu_workers[], .workers[]' "$SCRIPT_DIR/machines.yaml" -o json | jq -c '.' | while read -r machine; do
    uuid=$(echo "$machine" | jq -r '.uuid')
    if [[ "$uuid" != *"REPLACE"* ]]; then
        echo "$uuid"
    fi
done > /tmp/worker_uuids.txt

# Update ControlPlane section with all control plane machines
print -P "%F{yellow}Updating ControlPlane section...%f"
CONTROL_MACHINES=$(cat /tmp/control_plane_uuids.txt | sed 's/^/  - /' | tr '\n' '\n')

# Find and replace the ControlPlane section
TEMP_FILE=$(mktemp)
awk '
/^kind: ControlPlane$/ {
    print
    print "machines:"
    while ((getline line < "/tmp/control_plane_uuids.txt") > 0) {
        print "  - " line
    }
    # Skip old machines section until we hit patches or next kind
    getline
    while ($0 ~ /^machines:/ || $0 ~ /^  - /) {
        getline
    }
    print
    next
}
/^kind: Workers$/ {
    print
    print "machines:"
    while ((getline line < "/tmp/worker_uuids.txt") > 0) {
        print "  - " line
    }
    # Skip to next line (which should be ---)
    getline
    if ($0 == "---") print
    next
}
{ print }
' "$OUTPUT_FILE" > "$TEMP_FILE"

mv "$TEMP_FILE" "$OUTPUT_FILE"
rm -f /tmp/control_plane_uuids.txt /tmp/worker_uuids.txt

print -P "%F{green}✓%f Updated machine assignments"
echo ""

# Parse machines.yaml and generate Machine documents
print -P "%F{yellow}Processing machine inventory...%f"
echo ""

# Control Plane Nodes
print -P "%F{cyan}Control Plane Nodes:%f"
yq eval '.control_plane[]' "$SCRIPT_DIR/machines.yaml" -o json | jq -c '.' | while read -r machine; do
    uuid=$(echo "$machine" | jq -r '.uuid')
    name=$(echo "$machine" | jq -r '.name')
    ip=$(echo "$machine" | jq -r '.ip')
    
    if [[ "$uuid" == *"REPLACE"* ]]; then
        print -P "  %F{yellow}⚠%f  Skipping $name (UUID not set)"
        continue
    fi
    
    cat >> "$OUTPUT_FILE" <<EOF
---
kind: Machine
name: ${uuid}
patches:
  - name: set-hostname-${name}
    inline:
      machine:
        network:
          hostname: ${name}
        nodeLabels:
          node-role: control-plane
          management-ip: "${ip}"
          topology.kubernetes.io/zone: proxmox
  - name: control-plane-config
    file: patches/control-plane.yaml
EOF
    
    print -P "  %F{green}✓%f $name → ${uuid:0:12}..."
done

# GPU Worker Nodes
echo ""
print -P "%F{cyan}GPU Worker Nodes:%f"
yq eval '.gpu_workers[]' "$SCRIPT_DIR/machines.yaml" -o json | jq -c '.' | while read -r machine; do
    uuid=$(echo "$machine" | jq -r '.uuid')
    name=$(echo "$machine" | jq -r '.name')
    ip=$(echo "$machine" | jq -r '.ip')
    
    if [[ "$uuid" == *"REPLACE"* ]]; then
        print -P "  %F{yellow}⚠%f  Skipping $name (UUID not set)"
        continue
    fi
    
    cat >> "$OUTPUT_FILE" <<EOF
---
kind: Machine
name: ${uuid}
patches:
  - name: set-hostname-${name}
    inline:
      machine:
        network:
          hostname: ${name}
        nodeLabels:
          node-role: gpu-worker
          management-ip: "${ip}"
          topology.kubernetes.io/zone: proxmox
          nvidia.com/gpu: "true"
  - name: gpu-worker-config
    file: patches/gpu-worker.yaml
EOF
    
    print -P "  %F{green}✓%f $name → ${uuid:0:12}..."
done

# Regular Worker Nodes
echo ""
print -P "%F{cyan}Regular Worker Nodes:%f"
yq eval '.workers[]' "$SCRIPT_DIR/machines.yaml" -o json | jq -c '.' | while read -r machine; do
    uuid=$(echo "$machine" | jq -r '.uuid')
    name=$(echo "$machine" | jq -r '.name')
    ip=$(echo "$machine" | jq -r '.ip')
    
    if [[ "$uuid" == *"REPLACE"* ]]; then
        print -P "  %F{yellow}⚠%f  Skipping $name (UUID not set)"
        continue
    fi
    
    cat >> "$OUTPUT_FILE" <<EOF
---
kind: Machine
name: ${uuid}
patches:
  - name: set-hostname-${name}
    inline:
      machine:
        network:
          hostname: ${name}
        nodeLabels:
          node-role: worker
          management-ip: "${ip}"
          topology.kubernetes.io/zone: proxmox
  - name: regular-worker-config
    file: patches/regular-worker.yaml
EOF
    
    print -P "  %F{green}✓%f $name → ${uuid:0:12}..."
done

echo ""
print -P "%F{blue}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%f"
print -P "%F{green}✓ Cluster template generated:%f $OUTPUT_FILE"
print -P "%F{blue}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%f"
echo ""

print -P "%F{yellow}To apply this template:%f"
print -P "  cd %F{cyan}$SCRIPT_DIR%f"
print -P "  omnictl cluster template sync -f cluster-template.yaml"
echo ""
print -P "%F{red}⚠  Nodes will reboot to apply hostname and config changes%f"
echo ""

read -q "REPLY?Apply template now? (y/N) "
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    print -P "%F{yellow}Applying cluster template...%f"
    
    cd "$SCRIPT_DIR"
    if omnictl cluster template sync -f cluster-template.yaml 2>&1; then
        echo ""
        print -P "%F{green}✓ Template applied successfully!%f"
        echo ""
        print -P "Monitor node status:"
        print -P "  %F{cyan}watch 'kubectl get nodes -o wide'%f"
        echo ""
        print -P "Expected node names:"
        yq eval '.control_plane[].name, .gpu_workers[].name, .workers[].name' "$SCRIPT_DIR/machines.yaml" | while read -r name; do
            print -P "  • %F{green}${name}%f"
        done
    else
        echo ""
        print -P "%F{red}✗ Failed to apply template%f"
        exit 1
    fi
else
    echo ""
    echo "Template saved. Apply later with:"
    print -P "  cd %F{cyan}$SCRIPT_DIR%f"
    print -P "  omnictl cluster template sync -f cluster-template.yaml"
fi
