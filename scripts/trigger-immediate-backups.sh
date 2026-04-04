#!/bin/bash

# Script to trigger immediate backups for all volumes
# This bypasses the cron schedule and starts backups NOW

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Triggering Immediate Longhorn Backups${NC}"
echo -e "${BLUE}====================================${NC}"

# Function to check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}❌ kubectl not found${NC}"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        echo -e "${RED}❌ Cannot access Kubernetes cluster${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Cluster access verified${NC}"
}

# Function to get all Longhorn volumes
get_volumes() {
    echo -e "\n${CYAN}📦 Getting all Longhorn volumes...${NC}"
    kubectl get volumes -n longhorn-system --no-headers -o custom-columns="NAME:.metadata.name,STATE:.status.state" 2>/dev/null || {
        echo -e "${RED}❌ Could not get volumes. Is Longhorn running?${NC}"
        exit 1
    }
}

# Function to trigger backup for a specific volume
trigger_backup() {
    local volume_name="$1"
    local backup_name
    backup_name="manual-backup-$(date +%Y%m%d-%H%M%S)-${volume_name}"
    
    echo -e "${YELLOW}🔄 Creating backup for volume: $volume_name${NC}"
    
    cat <<EOF | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: Backup
metadata:
  name: $backup_name
  namespace: longhorn-system
  labels:
    longhornvolume: $volume_name
    backup-type: manual
    triggered-by: immediate-script
spec:
  volumeName: $volume_name
EOF

    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}✅ Backup job created: $backup_name${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed to create backup for: $volume_name${NC}"
        return 1
    fi
}

# Function to trigger backups by tier
trigger_tier_backups() {
    local tier="$1"
    echo -e "\n${CYAN}🎯 Triggering $tier tier backups...${NC}"
    
    # Get volumes with the specific recurring job label
    local volumes
    volumes=$(kubectl get volumes -n longhorn-system -l "recurring-job.longhorn.io/$tier=enabled" --no-headers -o custom-columns="NAME:.metadata.name" 2>/dev/null | grep -v "^$" || echo "")
    
    if [[ -z "$volumes" ]]; then
        echo -e "${YELLOW}⚠️ No volumes found for $tier tier${NC}"
        return 0
    fi
    
    local count=0
    while IFS= read -r volume; do
        if [[ -n "$volume" ]]; then
            trigger_backup "$volume"
            ((count++))
            # Small delay to avoid overwhelming the system
            sleep 2
        fi
    done <<< "$volumes"
    
    echo -e "${GREEN}📊 Triggered $count backups for $tier tier${NC}"
}

# Function to show backup progress
show_backup_progress() {
    echo -e "\n${CYAN}📊 Current backup status:${NC}"
    
    # Show recent backup jobs
    kubectl get backups -n longhorn-system --sort-by=.metadata.creationTimestamp -o custom-columns="NAME:.metadata.name,VOLUME:.spec.volumeName,STATE:.status.state,PROGRESS:.status.progress,CREATED:.metadata.creationTimestamp" --no-headers 2>/dev/null | tail -10 | while read line; do
        if [[ "$line" == *"InProgress"* ]]; then
            echo -e "   ${YELLOW}🔄 $line${NC}"
        elif [[ "$line" == *"Completed"* ]]; then
            echo -e "   ${GREEN}✅ $line${NC}"
        elif [[ "$line" == *"Error"* ]]; then
            echo -e "   ${RED}❌ $line${NC}"
        else
            echo -e "   ${BLUE}ℹ️ $line${NC}"
        fi
    done
}

# Function to run specific backup scenarios
run_backup_scenario() {
    local scenario="$1"
    
    case "$scenario" in
        "critical")
            echo -e "${RED}🔴 Running CRITICAL backups only${NC}"
            trigger_tier_backups "critical"
            ;;
        "important")
            echo -e "${YELLOW}🟡 Running IMPORTANT backups only${NC}"
            trigger_tier_backups "important"
            ;;
        "standard")
            echo -e "${BLUE}🔵 Running STANDARD backups only${NC}"
            trigger_tier_backups "standard"
            ;;
        "all")
            echo -e "${CYAN}🎯 Running ALL tier backups${NC}"
            trigger_tier_backups "critical"
            sleep 5
            trigger_tier_backups "important"
            sleep 5
            trigger_tier_backups "standard"
            ;;
        "test")
            echo -e "${CYAN}🧪 Running test backup (first volume only)${NC}"
            local test_volume
            test_volume=$(kubectl get volumes -n longhorn-system --no-headers -o custom-columns="NAME:.metadata.name" | head -1)
            if [[ -n "$test_volume" ]]; then
                trigger_backup "$test_volume"
            else
                echo -e "${RED}❌ No volumes found for test${NC}"
            fi
            ;;
        *)
            echo -e "${RED}❌ Unknown scenario: $scenario${NC}"
            echo -e "${BLUE}Valid scenarios: critical, important, standard, all, test${NC}"
            exit 1
            ;;
    esac
}

# Main function
main() {
    local scenario="${1:-all}"
    
    echo -e "${BLUE}🎯 Backup scenario: $scenario${NC}"
    
    check_kubectl
    
    # Show current volumes
    echo -e "\n${CYAN}📦 Current Longhorn volumes:${NC}"
    get_volumes
    
    # Run the backup scenario
    run_backup_scenario "$scenario"
    
    # Show progress
    sleep 3
    show_backup_progress
    
    echo -e "\n${GREEN}🎉 Backup jobs have been triggered!${NC}"
    echo -e "\n${BLUE}📋 Monitoring commands:${NC}"
    echo -e "• Watch backup progress: ${YELLOW}watch 'kubectl get backups -n longhorn-system'${NC}"
    echo -e "• Check backup details: ${YELLOW}kubectl describe backup <backup-name> -n longhorn-system${NC}"
    echo -e "• View in UI: ${YELLOW}http://your-longhorn-ui/backup${NC}"
    echo -e "• Check MinIO: ${YELLOW}http://192.168.10.133:9002${NC}"
    
    echo -e "\n${BLUE}💡 Run this script with different scenarios:${NC}"
    echo -e "• ${YELLOW}./trigger-immediate-backups.sh critical${NC} - Only critical volumes"
    echo -e "• ${YELLOW}./trigger-immediate-backups.sh important${NC} - Only important volumes"
    echo -e "• ${YELLOW}./trigger-immediate-backups.sh test${NC} - Single volume test"
    echo -e "• ${YELLOW}./trigger-immediate-backups.sh all${NC} - All volumes (default)"
}

# Execute main function with command line argument
main "$@"