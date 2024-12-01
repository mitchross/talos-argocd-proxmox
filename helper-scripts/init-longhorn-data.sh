#!/bin/bash
# longhorn-disk-init.sh
# Purpose: Initialize and configure SSDs for Longhorn storage on a single-node setup
# This script should be run after Longhorn is installed and running

# Color codes for better visibility
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Longhorn disk initialization...${NC}"

# Step 1: Label the node for storage
echo -e "${YELLOW}Labeling node for storage...${NC}"
kubectl label nodes vanillax-ai storage=true --overwrite
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Node labeled successfully${NC}"
else
    echo -e "${RED}Failed to label node${NC}"
    exit 1
fi

# Step 2: Wait for Longhorn manager to be ready
echo -e "${YELLOW}Waiting for Longhorn manager to be ready...${NC}"
while true; do
    if kubectl -n longhorn-system get pod -l app=longhorn-manager -o jsonpath='{.items[0].status.phase}' | grep -q Running; then
        echo -e "${GREEN}Longhorn manager is ready${NC}"
        break
    fi
    echo -n "."
    sleep 5
done

# Step 3: Get the Longhorn manager pod name
MANAGER_POD=$(kubectl -n longhorn-system get pod -l app=longhorn-manager -o jsonpath='{.items[0].metadata.name}')
echo -e "${GREEN}Found Longhorn manager pod: $MANAGER_POD${NC}"

# Step 4: Define the SSDs and their properties
declare -A disks=(
    ["ssd1"]="/mnt/PNY232323060701001C5"
    ["ssd2"]="/mnt/PNY232323060701001C1"
    ["ssd3"]="/mnt/PNY232323060701001BD"
    ["ssd4"]="/mnt/PNY232323060701001C6"
)

# Step 5: Verify disk paths exist
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

# Step 6: Disable the default disk
echo -e "${YELLOW}Disabling default disk...${NC}"
kubectl -n longhorn-system exec $MANAGER_POD -- \
    longhorn-manager disk update \
    --node vanillax-ai \
    --path /var/lib/longhorn \
    --disable-scheduling true

# Step 7: Add each SSD to Longhorn
echo -e "${YELLOW}Adding SSDs to Longhorn...${NC}"
for disk_name in "${!disks[@]}"; do
    path="${disks[$disk_name]}"
    echo -e "${GREEN}Configuring disk $disk_name at path $path${NC}"
    
    # Add the disk with specific configurations
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

# Step 8: Verify the setup
echo -e "${YELLOW}Verifying disk setup...${NC}"
kubectl -n longhorn-system get nodes.longhorn.io -o yaml > longhorn-node-config.yaml
echo -e "${GREEN}Disk configuration saved to longhorn-node-config.yaml${NC}"

# Step 9: Set up monitoring
echo -e "${YELLOW}Setting up disk monitoring...${NC}"
cat << 'EOF' > monitor-longhorn-disks.sh
#!/bin/bash
watch -n 5 "kubectl -n longhorn-system get nodes.longhorn.io -o custom-columns=NAME:.metadata.name,READY:.status.ready,SCHEDULABLE:.spec.allowScheduling,DISKS:.status.diskStatus[*].path,USED:.status.diskStatus[*].storageScheduled"
EOF
chmod +x monitor-longhorn-disks.sh

echo -e "${GREEN}Setup complete!${NC}"
echo -e "${YELLOW}To monitor your disks, run: ./monitor-longhorn-disks.sh${NC}"