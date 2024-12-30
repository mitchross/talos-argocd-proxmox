#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Validating Storage Configurations ==="

# Find all yaml files
YAML_FILES=$(find . -type f -name "*.yaml" -o -name "*.yml")

# Initialize counters
ERRORS=0
WARNINGS=0

for file in $YAML_FILES; do
    # Skip files in .git directory
    if [[ $file == *".git"* ]]; then
        continue
    fi

    # Check if file contains PV or PVC
    if grep -q "kind: PersistentVolume\|kind: PersistentVolumeClaim" "$file"; then
        echo -e "\nChecking file: ${YELLOW}$file${NC}"
        
        # Check PV naming
        PV_NAMES=$(grep -A1 "kind: PersistentVolume" "$file" | grep "name:" | awk '{print $2}')
        for pv in $PV_NAMES; do
            if [[ ! $pv =~ -pv$ ]]; then
                echo -e "${RED}ERROR: PV name '$pv' should end with '-pv'${NC}"
                ERRORS=$((ERRORS + 1))
            fi
        done

        # Check PVC naming
        PVC_NAMES=$(grep -A1 "kind: PersistentVolumeClaim" "$file" | grep "name:" | awk '{print $2}')
        for pvc in $PVC_NAMES; do
            if [[ ! $pvc =~ -pvc$ ]]; then
                echo -e "${RED}ERROR: PVC name '$pvc' should end with '-pvc'${NC}"
                ERRORS=$((ERRORS + 1))
            fi
        done

        # Check for labels
        if ! grep -q "labels:" "$file"; then
            echo -e "${RED}ERROR: Missing labels in $file${NC}"
            ERRORS=$((ERRORS + 1))
        fi

        # Check for storageClassName
        if ! grep -q "storageClassName:" "$file"; then
            echo -e "${RED}ERROR: Missing storageClassName in $file${NC}"
            ERRORS=$((ERRORS + 1))
        fi

        # Check for nodeAffinity in PVs
        if grep -q "kind: PersistentVolume" "$file"; then
            if ! grep -q "nodeAffinity:" "$file"; then
                echo -e "${RED}ERROR: Missing nodeAffinity in PV in $file${NC}"
                ERRORS=$((ERRORS + 1))
            fi
        fi

        # Check for namespace in PVCs
        if grep -q "kind: PersistentVolumeClaim" "$file"; then
            if ! grep -q "namespace:" "$file"; then
                echo -e "${RED}ERROR: Missing namespace in PVC in $file${NC}"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    fi
done

echo -e "\n=== Validation Summary ==="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All storage configurations are valid${NC}"
else
    echo -e "${RED}✗ Found $ERRORS error(s)${NC}"
fi

# Exit with error if any issues found
[ $ERRORS -eq 0 ] || exit 1 