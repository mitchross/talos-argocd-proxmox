#!/bin/bash

# Script to ensure all Longhorn PVCs have proper backup annotations
# This script analyzes PVCs and adds appropriate backup tier annotations

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Scanning for Longhorn PVCs without backup annotations...${NC}"

# Define backup tiers based on application criticality
declare -A BACKUP_TIERS=(
    # Critical - Databases and core infrastructure
    ["redis"]=critical
    ["postgres"]=critical
    ["postgresql"]=critical
    ["database"]=critical
    ["cloudnative-pg"]=critical
    
    # Important - User data and configurations
    ["immich"]=important
    ["home-assistant"]=important
    ["paperless"]=important
    ["frigate"]=important
    ["khoj"]=important
    ["ollama"]=important
    ["plex"]=important
    ["hoarder"]=important
    
    # Standard - Everything else (cache, logs, development)
    ["default"]=standard
    ["cache"]=standard
    ["nginx"]=standard
    ["jellyfin"]=standard
    ["tubearchivist"]=standard
    ["homepage"]=standard
    ["proxitok"]=standard
    ["searx"]=standard
    ["nestmtx"]=standard
)

# Function to determine backup tier based on namespace and PVC name
determine_backup_tier() {
    local namespace="$1"
    local pvc_name="$2"
    
    # Check namespace patterns
    for pattern in "${!BACKUP_TIERS[@]}"; do
        if [[ "$namespace" == *"$pattern"* ]] || [[ "$pvc_name" == *"$pattern"* ]]; then
            echo "${BACKUP_TIERS[$pattern]}"
            return
        fi
    done
    
    # Special cases
    if [[ "$namespace" == "monitoring" ]]; then
        echo "important"  # Monitoring data is important
    elif [[ "$namespace" == "infrastructure"* ]]; then
        echo "important"  # Infrastructure components
    elif [[ "$namespace" == *"ai"* ]] || [[ "$namespace" == "comfyui" ]] || [[ "$namespace" == "ollama"* ]]; then
        echo "important"  # AI workloads
    else
        echo "standard"   # Default tier
    fi
}

# Function to check if PVC has backup annotations
has_backup_annotations() {
    local file="$1"
    grep -q "longhorn.io/recurring-job-source.*enabled" "$file" && \
    grep -q "longhorn.io/recurring-job-group" "$file"
}

# Function to add backup annotations to PVC
add_backup_annotations() {
    local file="$1"
    local tier="$2"
    local namespace
    
    # Extract namespace from file path or content
    if grep -q "namespace:" "$file"; then
        namespace=$(grep "namespace:" "$file" | head -1 | awk '{print $2}')
    else
        namespace=$(echo "$file" | sed 's|.*/\([^/]*\)/[^/]*\.yaml|\1|')
    fi
    
    echo -e "${YELLOW}📝 Adding $tier backup annotations to: $file${NC}"
    
    # Check if annotations section exists
    if grep -q "annotations:" "$file"; then
        # Add to existing annotations section
        sed -i "/annotations:/a\\    # Longhorn backup settings - $(echo $tier | sed 's/.*/\u&/') tier\\    longhorn.io/recurring-job-source: enabled\\    longhorn.io/recurring-job-group: $tier\\    volume.beta.kubernetes.io/storage-provisioner: driver.longhorn.io" "$file"
    else
        # Add annotations section after labels or metadata
        if grep -q "labels:" "$file"; then
            sed -i "/labels:/,/^[[:space:]]*[^[:space:]]/ {
                /^[[:space:]]*[^[:space:]]/ {
                    /labels:/!i\\  annotations:\\    # Longhorn backup settings - $(echo $tier | sed 's/.*/\u&/') tier\\    longhorn.io/recurring-job-source: enabled\\    longhorn.io/recurring-job-group: $tier\\    volume.beta.kubernetes.io/storage-provisioner: driver.longhorn.io
                }
            }" "$file"
        else
            # Add after name line in metadata
            sed -i "/name:.*$/a\\  annotations:\\    # Longhorn backup settings - $(echo $tier | sed 's/.*/\u&/') tier\\    longhorn.io/recurring-job-source: enabled\\    longhorn.io/recurring-job-group: $tier\\    volume.beta.kubernetes.io/storage-provisioner: driver.longhorn.io" "$file"
        fi
    fi
}

# Find all PVC files with longhorn storage class
echo -e "${BLUE}🔍 Finding all Longhorn PVCs...${NC}"
LONGHORN_PVCS=()
while IFS= read -r -d '' file; do
    if grep -q "storageClassName:.*longhorn" "$file" && grep -q "kind: PersistentVolumeClaim" "$file"; then
        LONGHORN_PVCS+=("$file")
    fi
done < <(find /home/vanillax/programming/k3s-argocd-proxmox -name "*.yaml" -type f -print0)

# Also check for PVCs in Helm values files
while IFS= read -r -d '' file; do
    if grep -q "storageClassName:.*longhorn" "$file" && [[ "$file" == *"values.yaml" ]]; then
        LONGHORN_PVCS+=("$file")
    fi
done < <(find /home/vanillax/programming/k3s-argocd-proxmox -name "values.yaml" -type f -print0)

echo -e "${GREEN}📊 Found ${#LONGHORN_PVCS[@]} files with Longhorn storage${NC}"

# Process each PVC
UPDATED_COUNT=0
ALREADY_CONFIGURED=0

for pvc_file in "${LONGHORN_PVCS[@]}"; do
    echo -e "\n${BLUE}🔍 Checking: $pvc_file${NC}"
    
    # Skip if already has backup annotations
    if has_backup_annotations "$pvc_file"; then
        echo -e "${GREEN}✅ Already configured for backups${NC}"
        ((ALREADY_CONFIGURED++))
        continue
    fi
    
    # Extract namespace and PVC name for tier determination
    namespace=""
    pvc_name=""
    
    if grep -q "namespace:" "$pvc_file"; then
        namespace=$(grep "namespace:" "$pvc_file" | head -1 | awk '{print $2}')
    fi
    
    if grep -q "name:" "$pvc_file" && grep -B5 -A5 "name:" "$pvc_file" | grep -q "kind: PersistentVolumeClaim"; then
        pvc_name=$(grep "name:" "$pvc_file" | head -1 | awk '{print $2}')
    fi
    
    # Determine appropriate backup tier
    backup_tier=$(determine_backup_tier "$namespace" "$pvc_name")
    
    echo -e "${YELLOW}📋 Namespace: $namespace, PVC: $pvc_name, Tier: $backup_tier${NC}"
    
    # Add backup annotations
    add_backup_annotations "$pvc_file" "$backup_tier"
    ((UPDATED_COUNT++))
done

echo -e "\n${GREEN}✅ Backup Configuration Summary:${NC}"
echo -e "${GREEN}   - Files updated: $UPDATED_COUNT${NC}"
echo -e "${GREEN}   - Already configured: $ALREADY_CONFIGURED${NC}"
echo -e "${GREEN}   - Total Longhorn PVCs: ${#LONGHORN_PVCS[@]}${NC}"

echo -e "\n${BLUE}📋 Backup Tier Distribution:${NC}"
echo -e "${RED}🔴 Critical:${NC} Databases (hourly snapshots + daily backups)"
echo -e "${YELLOW}🟡 Important:${NC} User data, configurations (4-hour snapshots + daily backups)"
echo -e "${BLUE}🔵 Standard:${NC} Cache, logs, development (daily snapshots + weekly backups)"

echo -e "\n${GREEN}🎯 Next Steps:${NC}"
echo -e "1. Review the changes with: git diff"
echo -e "2. Commit the changes: git add . && git commit -m 'Add Longhorn backup annotations to all PVCs'"
echo -e "3. Push changes: git push"
echo -e "4. Verify backup jobs are running: kubectl get recurringjobs -n longhorn-system"
echo -e "5. Check MinIO bucket for backups: http://your-truenas-ip:9002"

echo -e "\n${BLUE}💡 To verify backups are working:${NC}"
echo "kubectl get backups -n longhorn-system"
echo "kubectl get volumes -n longhorn-system"