#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Validating Storage Configurations ==="

# Find all yaml files, excluding .git and arr directories
YAML_FILES=$(find . -type f \( -name "*.yaml" -o -name "*.yml" \) -not -path "*/\.*" -not -path "*/arr/*")

# Initialize counters
ERRORS=0
WARNINGS=0

check_file() {
    local file=$1
    local has_errors=0

    echo -e "\nChecking file: ${YELLOW}$file${NC}"

    # Get file contents
    content=$(cat "$file")

    # Check PV naming and configuration
    while IFS= read -r line; do
        if [[ $line =~ name:[[:space:]]*(.*) ]] && [[ $(echo "$content" | grep -B2 "$line" | grep -q "kind: PersistentVolume"; echo $?) -eq 0 ]]; then
            pv_name="${BASH_REMATCH[1]}"
            
            # Check if this is an SMB volume
            is_smb=0
            if echo "$content" | grep -A50 "kind: PersistentVolume" | grep -q "driver: smb.csi.k8s.io"; then
                is_smb=1
                echo -e "${GREEN}Found SMB storage configuration for $pv_name${NC}"
            fi
            
            # Only enforce -pv suffix for local storage
            if [[ $is_smb -eq 0 ]] && [[ ! $pv_name =~ -pv$ ]]; then
                echo -e "${RED}ERROR: Local storage PV name '$pv_name' should end with '-pv'${NC}"
                has_errors=1
            fi
        fi
    done < <(echo "$content")

    # Check PVC naming
    while IFS= read -r line; do
        if [[ $line =~ name:[[:space:]]*(.*) ]] && [[ $(echo "$content" | grep -B2 "$line" | grep -q "kind: PersistentVolumeClaim"; echo $?) -eq 0 ]]; then
            pvc_name="${BASH_REMATCH[1]}"
            
            # Check if this PVC references an SMB volume
            is_smb_pvc=0
            if echo "$content" | grep -A10 "kind: PersistentVolumeClaim" | grep -q "ReadWriteMany"; then
                # Check corresponding PV if volumeName is specified
                volume_name=$(echo "$content" | grep -A10 "kind: PersistentVolumeClaim" | grep "volumeName:" | awk '{print $2}')
                if [[ -n $volume_name ]]; then
                    # Search for the PV in all yaml files
                    if find . -type f -name "*.yaml" -exec grep -l "name: $volume_name" {} \; | xargs grep -l "driver: smb.csi.k8s.io" > /dev/null; then
                        is_smb_pvc=1
                        echo -e "${GREEN}Found SMB PVC configuration for $pvc_name${NC}"
                    fi
                fi
            fi
            
            # Only enforce -pvc suffix for local storage
            if [[ $is_smb_pvc -eq 0 ]] && [[ ! $pvc_name =~ -pvc$ ]]; then
                echo -e "${RED}ERROR: Local storage PVC name '$pvc_name' should end with '-pvc'${NC}"
                has_errors=1
            fi
        fi
    done < <(echo "$content")

    # Check for required fields in PVs
    if echo "$content" | grep -q "kind: PersistentVolume"; then
        # Only check these for local storage PVs
        if ! echo "$content" | grep -q "driver: smb.csi.k8s.io"; then
            if ! echo "$content" | grep -q "labels:"; then
                echo -e "${RED}ERROR: Missing labels in local storage PV${NC}"
                has_errors=1
            fi
            if ! echo "$content" | grep -q "nodeAffinity:"; then
                echo -e "${RED}ERROR: Missing nodeAffinity in local storage PV${NC}"
                has_errors=1
            fi
        fi
    fi

    # Check for required fields in PVCs
    if echo "$content" | grep -q "kind: PersistentVolumeClaim"; then
        if ! echo "$content" | grep -q "namespace:"; then
            echo -e "${RED}ERROR: Missing namespace in PVC${NC}"
            has_errors=1
        fi
        # Only check selector for local storage PVCs
        if ! echo "$content" | grep -q "ReadWriteMany"; then
            if ! echo "$content" | grep -q "selector:"; then
                echo -e "${RED}ERROR: Missing selector in local storage PVC${NC}"
                has_errors=1
            fi
        fi
    fi

    return $has_errors
}

for file in $YAML_FILES; do
    # Check if file contains PV or PVC
    if grep -q "kind: PersistentVolume\|kind: PersistentVolumeClaim" "$file"; then
        check_file "$file"
        if [ $? -eq 1 ]; then
            ERRORS=$((ERRORS + 1))
        fi
    fi
done

echo -e "\n=== Validation Summary ==="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All storage configurations are valid${NC}"
else
    echo -e "${RED}✗ Found issues in $ERRORS file(s)${NC}"
fi

# Exit with error if any issues found
[ $ERRORS -eq 0 ] || exit 1 