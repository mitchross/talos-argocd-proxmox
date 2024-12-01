#!/bin/bash
# longhorn-disk-cleanup.sh
# Purpose: Clean up previous Longhorn data from SSDs before reinitializing

# Color codes for better visibility
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Longhorn disk cleanup...${NC}"

# Define the disk paths
DISK_PATHS=(
    "/mnt/PNY232323060701001C5"
    "/mnt/PNY232323060701001C1"
    "/mnt/PNY232323060701001BD"
    "/mnt/PNY232323060701001C6"
)

# First, let's make sure Longhorn is completely removed
echo -e "${YELLOW}Ensuring Longhorn is uninstalled...${NC}"
kubectl delete namespace longhorn-system --wait=true 2>/dev/null || true
sleep 10  # Give some time for cleanup

# Clean up each disk
for disk_path in "${DISK_PATHS[@]}"; do
    echo -e "${YELLOW}Cleaning up disk: $disk_path${NC}"
    
    # Check if the path exists
    if [ ! -d "$disk_path" ]; then
        echo -e "${RED}Path $disk_path does not exist, skipping...${NC}"
        continue
    fi
    
    # Check if the disk is mounted
    if mountpoint -q "$disk_path"; then
        echo -e "${YELLOW}Unmounting $disk_path${NC}"
        sudo umount "$disk_path"
    fi
    
    # Remove Longhorn data
    echo -e "${YELLOW}Removing Longhorn data from $disk_path${NC}"
    sudo rm -rf "$disk_path/longhorn"*
    
    # Clean any replica directories
    sudo rm -rf "$disk_path"/replicas
    
    # Remove any remaining Longhorn metadata
    sudo rm -rf "$disk_path"/.longhorn
    
    echo -e "${GREEN}Cleaned up $disk_path${NC}"
done

# Also clean up any remaining Longhorn data in the default location
echo -e "${YELLOW}Cleaning up default Longhorn directory...${NC}"
sudo rm -rf /var/lib/longhorn/*

echo -e "${GREEN}Cleanup complete! You can now proceed with fresh Longhorn installation.${NC}"
echo -e "${YELLOW}Important: If these disks contain any other important data, make sure it's backed up before proceeding.${NC}"