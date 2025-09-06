#!/bin/bash

# Longhorn Disaster Recovery Script
# Restores volumes from MinIO S3 backups after complete cluster rebuild

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${RED}🚨 LONGHORN DISASTER RECOVERY${NC}"
echo -e "${RED}=============================${NC}"
echo -e "${YELLOW}⚠️  This script restores volumes from backups after cluster rebuild${NC}"
echo -e "${YELLOW}⚠️  Make sure Longhorn is installed and backup target is configured${NC}"

# Configuration
BACKUP_TARGET_URL="s3://longhorn-backups@us-east-1/"
DRY_RUN=${DRY_RUN:-false}
TIER=${1:-""}

# MinIO/S3 structure info
# Your MinIO has this structure:
# longhorn-backups/backupstore/volumes/XX/YY/pvc-uuid/backups/backup-name/
# This is the standard Longhorn backup store format

# Function to check prerequisites
check_prerequisites() {
    echo -e "\n${CYAN}📋 Checking prerequisites...${NC}"
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}❌ kubectl not found${NC}"
        exit 1
    fi
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        echo -e "${RED}❌ Cannot connect to cluster${NC}"
        exit 1
    fi
    
    # Check if Longhorn is installed
    if ! kubectl get namespace longhorn-system &> /dev/null; then
        echo -e "${RED}❌ Longhorn not installed. Install Longhorn first!${NC}"
        exit 1
    fi
    
    # Check backup target
    if ! kubectl get backuptarget default -n longhorn-system &> /dev/null; then
        echo -e "${RED}❌ Backup target not configured. Configure backup target first!${NC}"
        exit 1
    fi
    
    # Check if backup target is available
    local target_status=$(kubectl get backuptarget default -n longhorn-system -o jsonpath='{.status.available}' || echo "false")
    if [[ "$target_status" != "true" ]]; then
        echo -e "${RED}❌ Backup target not available. Check MinIO connection!${NC}"
        echo -e "${BLUE}💡 Run: kubectl describe backuptarget default -n longhorn-system${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Prerequisites met${NC}"
}

# Function to list available backups
list_backups() {
    echo -e "\n${CYAN}📦 Available backups in MinIO:${NC}"
    
    # Force rescan of backup target
    kubectl annotate backuptarget default -n longhorn-system \
        longhorn.io/last-applied-backup-target-url- --overwrite || true
    
    # Wait for rescan
    sleep 5
    
    # List backups
    kubectl get backups -n longhorn-system -o custom-columns=\
"NAME:.metadata.name,VOLUME:.spec.volumeName,SIZE:.status.size,STATE:.status.state,CREATED:.metadata.creationTimestamp" \
        --sort-by=.metadata.creationTimestamp
}

# Function to create restore plan
create_restore_plan() {
    local tier="$1"
    
    echo -e "\n${CYAN}📋 Creating restore plan for tier: $tier${NC}"
    
    # Define application mappings and priorities
    declare -A RESTORE_PRIORITY=(
        # Critical tier - restore first
        ["redis"]=1
        ["postgres"]=1
        ["postgresql"]=1
        ["registry"]=1
        
        # Important tier - restore second
        ["immich"]=2
        ["home-assistant"]=2
        ["paperless"]=2
        ["prometheus"]=2
        ["grafana"]=2
        ["alertmanager"]=2
        ["khoj"]=2
        ["frigate"]=2
        ["ollama"]=2
        
        # Standard tier - restore last
        ["jellyfin"]=3
        ["nginx"]=3
        ["homepage"]=3
        ["tubearchivist"]=3
        ["hoarder"]=3
        ["proxitok"]=3
        ["searx"]=3
    )
    
    # Get backups for tier
    local backups
    case "$tier" in
        "critical")
            backups=$(kubectl get backups -n longhorn-system -l "data-tier=critical" --no-headers -o custom-columns="NAME:.metadata.name,VOLUME:.spec.volumeName" 2>/dev/null || echo "")
            ;;
        "important")
            backups=$(kubectl get backups -n longhorn-system -l "data-tier=important" --no-headers -o custom-columns="NAME:.metadata.name,VOLUME:.spec.volumeName" 2>/dev/null || echo "")
            ;;
        "standard")
            backups=$(kubectl get backups -n longhorn-system -l "data-tier=standard" --no-headers -o custom-columns="NAME:.metadata.name,VOLUME:.spec.volumeName" 2>/dev/null || echo "")
            ;;
        "all")
            backups=$(kubectl get backups -n longhorn-system --no-headers -o custom-columns="NAME:.metadata.name,VOLUME:.spec.volumeName" 2>/dev/null || echo "")
            ;;
        *)
            echo -e "${RED}❌ Invalid tier: $tier${NC}"
            echo -e "${BLUE}Valid tiers: critical, important, standard, all${NC}"
            return 1
            ;;
    esac
    
    if [[ -z "$backups" ]]; then
        echo -e "${YELLOW}⚠️ No backups found for tier: $tier${NC}"
        return 0
    fi
    
    echo "$backups"
}

# Function to restore a volume from backup
restore_volume() {
    local backup_name="$1"
    local original_volume="$2"
    
    echo -e "\n${BLUE}🔄 Restoring volume: $original_volume from backup: $backup_name${NC}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}🧪 DRY RUN: Would restore $backup_name -> $original_volume${NC}"
        return 0
    fi
    
    # Generate restored volume name
    local restored_volume="restored-$(date +%Y%m%d)-${original_volume}"
    
    # Create volume from backup
    # Note: The backup URL structure matches your MinIO layout
    cat <<EOF | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: $restored_volume
  namespace: longhorn-system
  labels:
    restored-from: $backup_name
    original-volume: $original_volume
    restoration-date: $(date +%Y-%m-%d)
spec:
  fromBackup: $backup_name
  numberOfReplicas: 3
  size: "50Gi"  # Will be adjusted automatically from backup metadata
EOF

    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}✅ Restore job created for: $original_volume${NC}"
        
        # Wait for restore to start
        echo -e "${YELLOW}⏳ Waiting for restore to begin...${NC}"
        sleep 10
        
        # Check restore status
        local status=$(kubectl get volume "$restored_volume" -n longhorn-system -o jsonpath='{.status.state}' 2>/dev/null || echo "unknown")
        echo -e "${BLUE}📊 Restore status: $status${NC}"
        
        return 0
    else
        echo -e "${RED}❌ Failed to create restore job for: $original_volume${NC}"
        return 1
    fi
}

# Function to show restore progress
show_restore_progress() {
    echo -e "\n${CYAN}📊 Restore Progress:${NC}"
    
    # Show volumes being restored
    kubectl get volumes -n longhorn-system -l "restored-from" \
        -o custom-columns="NAME:.metadata.name,STATE:.status.state,SIZE:.spec.size,RESTORED-FROM:.metadata.labels.restored-from" \
        --no-headers 2>/dev/null | while read line; do
        if [[ "$line" == *"attached"* ]] || [[ "$line" == *"healthy"* ]]; then
            echo -e "   ${GREEN}✅ $line${NC}"
        elif [[ "$line" == *"restoring"* ]] || [[ "$line" == *"creating"* ]]; then
            echo -e "   ${YELLOW}🔄 $line${NC}"
        else
            echo -e "   ${BLUE}ℹ️ $line${NC}"
        fi
    done
}

# Function for guided restoration
guided_restoration() {
    echo -e "\n${CYAN}🎯 Starting Guided Disaster Recovery${NC}"
    
    echo -e "\n${BLUE}Phase 1: Critical Infrastructure (Databases, Core Services)${NC}"
    create_restore_plan "critical" | while read backup_name volume_name; do
        if [[ -n "$backup_name" && -n "$volume_name" ]]; then
            restore_volume "$backup_name" "$volume_name"
            sleep 5  # Prevent overwhelming the system
        fi
    done
    
    echo -e "\n${YELLOW}⏳ Waiting for critical services to restore...${NC}"
    sleep 30
    show_restore_progress
    
    echo -e "\n${BLUE}Phase 2: Important Data (User Data, Configurations)${NC}"
    read -p "Continue with important data restoration? [y/N]: " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        create_restore_plan "important" | while read backup_name volume_name; do
            if [[ -n "$backup_name" && -n "$volume_name" ]]; then
                restore_volume "$backup_name" "$volume_name"
                sleep 3
            fi
        done
    fi
    
    echo -e "\n${YELLOW}⏳ Waiting for important services to restore...${NC}"
    sleep 30
    show_restore_progress
    
    echo -e "\n${BLUE}Phase 3: Standard Data (Cache, Logs, Development)${NC}"
    read -p "Continue with standard data restoration? [y/N]: " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        create_restore_plan "standard" | while read backup_name volume_name; do
            if [[ -n "$backup_name" && -n "$volume_name" ]]; then
                restore_volume "$backup_name" "$volume_name"
                sleep 2
            fi
        done
    fi
    
    show_restore_progress
}

# Function to reconnect PVCs to restored volumes
reconnect_pvcs() {
    echo -e "\n${CYAN}🔗 Reconnecting PVCs to restored volumes${NC}"
    echo -e "${YELLOW}⚠️ This requires manual intervention - see the disaster recovery guide${NC}"
    
    echo -e "\n${BLUE}📋 Manual steps needed:${NC}"
    echo -e "1. Update PVC manifests to reference restored volumes"
    echo -e "2. Redeploy applications via ArgoCD"
    echo -e "3. Verify data integrity"
    
    echo -e "\n${BLUE}🔍 Current restored volumes:${NC}"
    kubectl get volumes -n longhorn-system -l "restored-from" \
        -o custom-columns="RESTORED-NAME:.metadata.name,ORIGINAL:.metadata.labels.original-volume,STATUS:.status.state"
}

# Main function
main() {
    local mode="${1:-guided}"
    
    case "$mode" in
        "--list"|"list")
            check_prerequisites
            list_backups
            ;;
        "--tier")
            local tier="$2"
            check_prerequisites
            create_restore_plan "$tier"
            ;;
        "--restore")
            local backup_name="$2"
            local volume_name="$3"
            check_prerequisites
            restore_volume "$backup_name" "$volume_name"
            ;;
        "--progress"|"progress")
            show_restore_progress
            ;;
        "--reconnect"|"reconnect")
            reconnect_pvcs
            ;;
        "--dry-run")
            export DRY_RUN=true
            check_prerequisites
            guided_restoration
            ;;
        "guided"|"")
            check_prerequisites
            list_backups
            guided_restoration
            reconnect_pvcs
            ;;
        *)
            echo -e "${RED}❌ Unknown mode: $mode${NC}"
            echo -e "\n${BLUE}Usage:${NC}"
            echo -e "${YELLOW}./restore-from-backups.sh${NC}                    - Guided restoration"
            echo -e "${YELLOW}./restore-from-backups.sh --list${NC}             - List available backups"
            echo -e "${YELLOW}./restore-from-backups.sh --tier critical${NC}     - Restore specific tier"
            echo -e "${YELLOW}./restore-from-backups.sh --dry-run${NC}           - Test without actual restore"
            echo -e "${YELLOW}./restore-from-backups.sh --progress${NC}          - Show restore progress"
            exit 1
            ;;
    esac
}

# Execute main function
main "$@"