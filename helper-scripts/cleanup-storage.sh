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
# Get all PVCs with finalizers and remove them
for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
    for pvc in $(kubectl get pvc -n $ns -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        echo "Removing finalizers from PVC $pvc in namespace $ns"
        kubectl patch pvc $pvc -n $ns -p '{"metadata":{"finalizers":null}}' --type=merge
    done
done

echo -e "\n${YELLOW}Step 2: Removing finalizers from PVs${NC}"
# Get all PVs with finalizers and remove them
for pv in $(kubectl get pv -o jsonpath='{.items[*].metadata.name}'); do
    echo "Removing finalizers from PV $pv"
    kubectl patch pv $pv -p '{"metadata":{"finalizers":null}}' --type=merge
done

echo -e "\n${YELLOW}Step 3: Force deleting PVCs${NC}"
kubectl delete pvc --all --all-namespaces --force --grace-period=0

echo -e "\n${YELLOW}Step 4: Force deleting PVs${NC}"
kubectl delete pv --all --force --grace-period=0

echo -e "\n${GREEN}Cleanup completed successfully!${NC}"
echo -e "You can now run the setup-storage.sh script to create the directories"
echo -e "and then apply your storage configurations through ArgoCD." 