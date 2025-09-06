#!/bin/bash

# Script to update PVC manifests to use restored volumes
# This prevents ArgoCD from creating new empty PVCs that conflict with restored data

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔗 MAPPING RESTORED VOLUMES TO PVC NAMES${NC}"
echo -e "${BLUE}=======================================${NC}"

# Function to get mapping between original and restored volumes
get_volume_mapping() {
    echo -e "\n${CYAN}📋 Getting volume mapping...${NC}"
    
    # Get all restored volumes and their original names
    kubectl get volumes -n longhorn-system -l "restored-from" \
        -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.metadata.labels.original-volume}{" "}{.metadata.labels.restored-from}{"\n"}{end}' \
        2>/dev/null | while read restored_name original_name backup_name; do
        if [[ -n "$restored_name" && -n "$original_name" ]]; then
            echo "$restored_name|$original_name|$backup_name"
        fi
    done
}

# Function to find PVC files that need updating
find_pvc_files() {
    local original_volume="$1"
    
    # Search for PVC files that might reference this volume
    # Look for storageClassName: longhorn in all YAML files
    find /home/vanillax/programming/k3s-argocd-proxmox -name "*.yaml" -type f \
        -exec grep -l "storageClassName.*longhorn" {} \; \
        -exec grep -l "kind: PersistentVolumeClaim" {} \; | sort | uniq
}

# Function to create PV that points to restored volume
create_persistent_volume() {
    local restored_volume="$1"
    local original_volume="$2"
    local pvc_name="$3"
    local namespace="$4"
    local size="$5"
    
    echo -e "${YELLOW}📦 Creating PersistentVolume for $restored_volume${NC}"
    
    # Create PV that references the restored Longhorn volume
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: restored-pv-${restored_volume}
  labels:
    restored-from-backup: "true"
    original-volume: "${original_volume}"
spec:
  capacity:
    storage: ${size}
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "3"
      staleReplicaTimeout: "30"
    volumeHandle: ${restored_volume}
  claimRef:
    name: ${pvc_name}
    namespace: ${namespace}
EOF
}

# Function to update application manifests
update_application_manifests() {
    echo -e "\n${CYAN}📝 Updating application manifests for disaster recovery...${NC}"
    
    # Create a disaster recovery patch directory
    local patch_dir="/tmp/disaster-recovery-patches"
    mkdir -p "$patch_dir"
    
    # Get volume mappings
    local mappings=$(get_volume_mapping)
    
    if [[ -z "$mappings" ]]; then
        echo -e "${RED}❌ No restored volumes found${NC}"
        return 1
    fi
    
    echo -e "${GREEN}📊 Found restored volumes:${NC}"
    echo "$mappings" | while IFS='|' read restored_name original_name backup_name; do
        echo -e "   ${BLUE}$original_name → $restored_name${NC}"
    done
    
    echo "$mappings" | while IFS='|' read restored_name original_name backup_name; do
        echo -e "\n${YELLOW}🔄 Processing volume: $original_name → $restored_name${NC}"
        
        # Get volume size from Longhorn
        local volume_size=$(kubectl get volume "$restored_name" -n longhorn-system -o jsonpath='{.spec.size}' 2>/dev/null || echo "10Gi")
        
        # Find PVC files that might use this volume
        # This is tricky - we need to map based on application patterns
        
        # Common application volume patterns
        case "$original_name" in
            *"immich"*)
                echo -e "   ${CYAN}📸 Found Immich volume${NC}"
                create_persistent_volume "$restored_name" "$original_name" "immich-data" "immich" "$volume_size"
                ;;
            *"home-assistant"*)
                echo -e "   ${CYAN}🏠 Found Home Assistant volume${NC}"
                create_persistent_volume "$restored_name" "$original_name" "home-assistant-config" "home-assistant" "$volume_size"
                ;;
            *"paperless"*)
                echo -e "   ${CYAN}📄 Found Paperless volume${NC}"
                # Paperless has multiple PVCs - need to determine which one
                if [[ "$original_name" == *"data"* ]]; then
                    create_persistent_volume "$restored_name" "$original_name" "paperless-data-pvc" "paperless-ngx" "$volume_size"
                elif [[ "$original_name" == *"media"* ]]; then
                    create_persistent_volume "$restored_name" "$original_name" "paperless-media-pvc" "paperless-ngx" "$volume_size"
                fi
                ;;
            *"redis"*)
                echo -e "   ${CYAN}🗄️ Found Redis volume${NC}"
                create_persistent_volume "$restored_name" "$original_name" "redis-data-redis-master-0" "redis-instance" "$volume_size"
                ;;
            *"prometheus"*)
                echo -e "   ${CYAN}📊 Found Prometheus volume${NC}"
                # Prometheus uses different PVC structure (via Helm)
                echo -e "   ${YELLOW}⚠️ Prometheus volumes need manual Helm values update${NC}"
                ;;
            *)
                echo -e "   ${YELLOW}❓ Unknown volume pattern: $original_name${NC}"
                echo -e "   ${BLUE}💡 Manual PV creation may be needed${NC}"
                ;;
        esac
    done
}

# Function to provide manual recovery instructions
provide_manual_instructions() {
    echo -e "\n${CYAN}📋 MANUAL STEPS REQUIRED${NC}"
    echo -e "${CYAN}========================${NC}"
    
    echo -e "\n${YELLOW}⚠️ Some applications may need manual PVC updates:${NC}"
    
    echo -e "\n${BLUE}1. For Helm-based applications (Prometheus, Grafana):${NC}"
    echo -e "   Update values.yaml files to reference restored volumes"
    echo -e "   Then redeploy via ArgoCD"
    
    echo -e "\n${BLUE}2. For StatefulSets (Elasticsearch, databases):${NC}"
    echo -e "   May need to scale down, update PVC references, scale up"
    
    echo -e "\n${BLUE}3. For complex applications:${NC}"
    echo -e "   Check application logs for PVC binding issues"
    echo -e "   kubectl get events --all-namespaces | grep -i pvc"
    
    echo -e "\n${GREEN}✅ Applications with simple PVCs should work automatically${NC}"
    echo -e "   (Immich, Home Assistant, Paperless, most user apps)"
    
    echo -e "\n${BLUE}🔍 Verification commands:${NC}"
    echo -e "   kubectl get pv | grep restored"
    echo -e "   kubectl get pvc --all-namespaces"
    echo -e "   kubectl get pods --all-namespaces | grep -v Running"
}

# Function to create disaster recovery mode ApplicationSet patches
create_disaster_recovery_patches() {
    echo -e "\n${CYAN}🚨 Creating disaster recovery mode patches...${NC}"
    
    # Create patch to prevent ApplicationSet from immediately deploying apps
    # This gives time to restore data first
    cat > /tmp/disable-applicationsets.yaml <<EOF
# Patch to disable ApplicationSets during disaster recovery
# Apply this BEFORE restoring data to prevent PVC conflicts

# Disable infrastructure ApplicationSet
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: infrastructure-appset
  namespace: argocd
spec:
  syncPolicy: {}  # Remove automated sync
---
# Disable monitoring ApplicationSet  
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: monitoring-appset
  namespace: argocd
spec:
  syncPolicy: {}  # Remove automated sync
---
# Disable user apps ApplicationSet
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: my-apps-appset
  namespace: argocd
spec:
  syncPolicy: {}  # Remove automated sync
EOF

    echo -e "${GREEN}✅ Created /tmp/disable-applicationsets.yaml${NC}"
    echo -e "${BLUE}💡 Apply this during disaster recovery to prevent app deployment${NC}"
}

# Main function
main() {
    local mode="${1:-auto}"
    
    case "$mode" in
        "check")
            get_volume_mapping
            ;;
        "create-pvs")
            update_application_manifests
            ;;
        "manual")
            provide_manual_instructions
            ;;
        "patches")
            create_disaster_recovery_patches
            ;;
        "auto"|"")
            update_application_manifests
            provide_manual_instructions
            create_disaster_recovery_patches
            ;;
        *)
            echo -e "${RED}❌ Unknown mode: $mode${NC}"
            echo -e "\n${BLUE}Usage:${NC}"
            echo -e "${YELLOW}./update-pvcs-for-restore.sh${NC}           - Full automatic mapping"
            echo -e "${YELLOW}./update-pvcs-for-restore.sh check${NC}      - Check restored volumes"
            echo -e "${YELLOW}./update-pvcs-for-restore.sh create-pvs${NC} - Create PVs only"
            echo -e "${YELLOW}./update-pvcs-for-restore.sh manual${NC}     - Show manual instructions"
            echo -e "${YELLOW}./update-pvcs-for-restore.sh patches${NC}    - Create DR patches"
            exit 1
            ;;
    esac
}

# Execute main function
main "$@"