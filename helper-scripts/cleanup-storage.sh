#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}WARNING: This script will delete all PVCs and PVs. Data may be lost.${NC}"
echo -e "Please make sure you have backed up any important data."
read -p "Are you sure you want to continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Aborting."
    exit 1
fi

echo -e "\n${YELLOW}Step 1: Removing finalizers from PVCs${NC}"
kubectl get pvc --all-namespaces -o json | jq '.items[] | select(.metadata.finalizers != null) | "kubectl patch pvc \(.metadata.name) -n \(.metadata.namespace) -p \"{\\"metadata\\":{\\"finalizers\\":[]}}\" --type=merge"' | xargs -I {} bash -c '{}'

echo -e "\n${YELLOW}Step 2: Removing finalizers from PVs${NC}"
kubectl get pv -o json | jq '.items[] | select(.metadata.finalizers != null) | "kubectl patch pv \(.metadata.name) -p \"{\\"metadata\\":{\\"finalizers\\":[]}}\" --type=merge"' | xargs -I {} bash -c '{}'

echo -e "\n${YELLOW}Step 3: Force deleting PVCs${NC}"
kubectl delete pvc --all --all-namespaces --force --grace-period=0

echo -e "\n${YELLOW}Step 4: Force deleting PVs${NC}"
kubectl delete pv --all --force --grace-period=0

echo -e "\n${GREEN}Cleanup completed successfully!${NC}"
echo -e "You can now run the setup-storage.sh script to create the directories"
echo -e "and then apply your storage configurations through ArgoCD." 