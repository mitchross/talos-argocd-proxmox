#!/bin/bash
# longhorn-disk-init.sh
# Purpose: Initialize and configure SSDs for Longhorn storage using the Longhorn CLI tool

# Color codes for better visibility
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# First, let's verify we have the CLI tool available
if ! command -v longhornctl &> /dev/null; then
    echo -e "${RED}Error: longhornctl not found${NC}"
    echo "Please install the Longhorn CLI tool first"
    exit 1
fi

echo -e "${YELLOW}Checking Longhorn CLI version...${NC}"
longhornctl version

# Check if Longhorn is installed and running
echo -e "${YELLOW}Checking Longhorn installation status...${NC}"
if ! longhornctl get node &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Longhorn. Is it installed and running?${NC}"
    exit 1
fi

# Label node for storage
echo -e "${YELLOW}Labeling node for storage...${NC}"
kubectl label nodes vanillax-ai storage=true --overwrite

# Define the SSDs and their properties
declare -A disks=(
    ["ssd1"]="/mnt/PNY232323060701001C5"
    ["ssd2"]="/mnt/PNY232323060701001C1"
    ["ssd3"]="/mnt/PNY232323060701001BD"
    ["ssd4"]="/mnt/PNY232323060701001C6"
)

# Verify disk paths and create if needed
echo -e "${YELLOW}Verifying disk paths...${NC}"
for disk_path in "${disks[@]}"; do
    if [ ! -d "$disk_path" ]; then
        echo -e "${RED}Warning: Path $disk_path does not exist${NC}"
        read -p "Create directory? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo mkdir -p "$disk_path"
            sudo chown root:root "$disk_path"
            sudo chmod 700 "$disk_path"
            echo -e "${GREEN}Created directory: $disk_path${NC}"
        else
            echo -e "${RED}Skipping disk path: $disk_path${NC}"
            continue
        fi
    fi
done

# Get current node status
echo -e "${YELLOW}Getting current node status...${NC}"
longhornctl get node vanillax-ai

# First, disable the default disk
echo -e "${YELLOW}Disabling default disk...${NC}"
longhornctl node update-disk \
    --node vanillax-ai \
    --path /var/lib/longhorn \
    --disable-scheduling=true \
    --eviction-requested=true

# Add each SSD
echo -e "${YELLOW}Adding SSDs to Longhorn...${NC}"
for disk_name in "${!disks[@]}"; do
    path="${disks[$disk_name]}"
    echo -e "${GREEN}Adding disk $disk_name at path $path${NC}"
    
    longhornctl node update-disk \
        --node vanillax-ai \
        --path "$path" \
        --tags "ssd" \
        --storage-reserved 10Gi \
        --disable-scheduling=false
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully added $disk_name${NC}"
    else
        echo -e "${RED}Failed to add $disk_name${NC}"
    fi
done

# Verify configuration
echo -e "${YELLOW}Verifying final configuration...${NC}"
echo -e "Node and disk status:"
longhornctl get node vanillax-ai

echo -e "\n${GREEN}Setup complete!${NC}"
echo -e "${YELLOW}Note: It may take a few moments for all disks to become ready.${NC}"
echo -e "${YELLOW}You can monitor the status using:${NC}"
echo -e "${GREEN}longhornctl get node vanillax-ai${NC}"