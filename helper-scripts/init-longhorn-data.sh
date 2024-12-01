#!/bin/bash
# longhorn-disk-init.sh
# Purpose: Initialize and configure SSDs for Longhorn storage on a single-node setup

# Color codes for better visibility
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Checking if Longhorn is installed...${NC}"

# Check if Longhorn namespace exists
if ! kubectl get namespace longhorn-system >/dev/null 2>&1; then
    echo -e "${RED}Error: Longhorn namespace not found!${NC}"
    echo -e "Please deploy Longhorn first using:"
    echo -e "${GREEN}kubectl apply -k /path/to/your/longhorn/directory${NC}"
    exit 1
fi

echo -e "${YELLOW}Waiting for Longhorn manager to be deployed...${NC}"
while true; do
    PODS=$(kubectl -n longhorn-system get pods -l app=longhorn-manager 2>/dev/null)
    if [ $? -eq 0 ] && echo "$PODS" | grep -q "1/1"; then
        echo -e "${GREEN}Longhorn manager is deployed${NC}"
        break
    fi
    echo -n "."
    sleep 5
done

# Continue with node labeling
echo -e "${YELLOW}Labeling node for storage...${NC}"
kubectl label nodes vanillax-ai storage=true --overwrite
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Node labeled successfully${NC}"
else
    echo -e "${RED}Failed to label node${NC}"
    exit 1
fi

# Get the Longhorn manager pod name with verification
echo -e "${YELLOW}Getting Longhorn manager pod name...${NC}"
while true; do
    MANAGER_POD=$(kubectl -n longhorn-system get pod -l app=longhorn-manager -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ ! -z "$MANAGER_POD" ]; then
        echo -e "${GREEN}Found Longhorn manager pod: $MANAGER_POD${NC}"
        break
    fi
    echo -n "."
    sleep 5
done

# Define the SSDs and their properties
declare -A disks=(
    ["ssd1"]="/mnt/PNY232323060701001C5"
    ["ssd2"]="/mnt/PNY232323060701001C1"
    ["ssd3"]="/mnt/PNY232323060701001BD"
    ["ssd4"]="/mnt/PNY232323060701001C6"
)

# Verify disk paths exist
echo -e "${YELLOW}Verifying disk paths...${NC}"
for disk_path in "${disks[@]}"; do
    if [ ! -d "$disk_path" ]; then
        echo -e "${RED}Warning: Path $disk_path does not exist${NC}"
        read -p "Create directory? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo mkdir -p "$disk_path"
            echo "Created directory: $disk_path"
        else
            echo -e "${RED}Skipping disk path: $disk_path${NC}"
            continue
        fi
    fi
done

# Disable the default disk
echo -e "${YELLOW}Disabling default disk...${NC}"
kubectl -n longhorn-system exec $MANAGER_POD -- \
    longhorn-manager disk update \
    --node vanillax-ai \
    --path /var/lib/longhorn \
    --disable-scheduling true

# Add each SSD to Longhorn
echo -e "${YELLOW}Adding SSDs to Longhorn...${NC}"
for disk_name in "${!disks[@]}"; do
    path="${disks[$disk_name]}"
    echo -e "${GREEN}Configuring disk $disk_name at path $path${NC}"
    
    kubectl -n longhorn-system exec $MANAGER_POD -- \
        longhorn-manager disk update \
        --node vanillax-ai \
        --path "$path" \
        --tags ssd \
        --storage-reserved 10Gi \
        --disable-scheduling false
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully added $disk_name${NC}"
    else
        echo -e "${RED}Failed to add $disk_name${NC}"
    fi
done

echo -e "${GREEN}Setup complete!${NC}"