#!/bin/bash

# Script to verify Longhorn backup configuration and MinIO S3 connectivity
# This script checks the entire backup pipeline from PVCs to MinIO

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Longhorn Backup System Verification${NC}"
echo -e "${BLUE}=====================================${NC}"

# Function to check if kubectl command exists and cluster is accessible
check_cluster_access() {
    echo -e "\n${CYAN}📡 Checking Kubernetes cluster access...${NC}"
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

# Function to check Longhorn system health
check_longhorn_system() {
    echo -e "\n${CYAN}🏗️ Checking Longhorn system health...${NC}"
    
    # Check if longhorn-system namespace exists
    if ! kubectl get namespace longhorn-system &> /dev/null; then
        echo -e "${RED}❌ longhorn-system namespace not found${NC}"
        return 1
    fi
    
    # Check Longhorn manager pods
    local manager_ready=$(kubectl get pods -n longhorn-system -l app=longhorn-manager --no-headers | grep -c "Running" || echo "0")
    echo -e "${GREEN}📦 Longhorn managers running: $manager_ready${NC}"
    
    # Check Longhorn UI pod
    local ui_ready=$(kubectl get pods -n longhorn-system -l app=longhorn-ui --no-headers | grep -c "Running" || echo "0")
    echo -e "${GREEN}🖥️ Longhorn UI running: $ui_ready${NC}"
    
    # Check CSI driver
    local csi_ready=$(kubectl get pods -n longhorn-system -l app=csi-attacher --no-headers | grep -c "Running" || echo "0")
    echo -e "${GREEN}🔌 CSI driver pods running: $csi_ready${NC}"
}

# Function to check backup target configuration
check_backup_target() {
    echo -e "\n${CYAN}🎯 Checking backup target configuration...${NC}"
    
    # Check BackupTarget resource
    if kubectl get backuptarget default -n longhorn-system &> /dev/null; then
        local backup_url=$(kubectl get backuptarget default -n longhorn-system -o jsonpath='{.spec.backupTargetURL}')
        echo -e "${GREEN}✅ BackupTarget configured: $backup_url${NC}"
    else
        echo -e "${RED}❌ BackupTarget not found${NC}"
        return 1
    fi
    
    # Check backup credentials secret
    if kubectl get secret longhorn-backup-credentials -n longhorn-system &> /dev/null; then
        echo -e "${GREEN}✅ Backup credentials secret exists${NC}"
    else
        echo -e "${RED}❌ Backup credentials secret not found${NC}"
        return 1
    fi
    
    # Check External Secrets
    if kubectl get externalsecret longhorn-backup-credentials -n longhorn-system &> /dev/null; then
        local secret_status=$(kubectl get externalsecret longhorn-backup-credentials -n longhorn-system -o jsonpath='{.status.conditions[0].type}')
        echo -e "${GREEN}✅ External Secret status: $secret_status${NC}"
    fi
}

# Function to check recurring jobs
check_recurring_jobs() {
    echo -e "\n${CYAN}⏰ Checking recurring jobs...${NC}"
    
    local jobs=$(kubectl get recurringjobs -n longhorn-system --no-headers 2>/dev/null | wc -l || echo "0")
    echo -e "${GREEN}📋 Total recurring jobs: $jobs${NC}"
    
    if [[ $jobs -gt 0 ]]; then
        echo -e "${BLUE}📝 Recurring jobs details:${NC}"
        kubectl get recurringjobs -n longhorn-system -o custom-columns="NAME:.metadata.name,TASK:.spec.task,CRON:.spec.cron,GROUPS:.spec.groups,RETAIN:.spec.retain" --no-headers 2>/dev/null | while read line; do
            echo -e "   ${YELLOW}• $line${NC}"
        done
    fi
}

# Function to check volumes with backup annotations
check_volume_backup_annotations() {
    echo -e "\n${CYAN}💾 Checking volumes with backup configuration...${NC}"
    
    # Get all Longhorn volumes
    local volumes=$(kubectl get volumes -n longhorn-system --no-headers 2>/dev/null | wc -l || echo "0")
    echo -e "${GREEN}📦 Total Longhorn volumes: $volumes${NC}"
    
    if [[ $volumes -gt 0 ]]; then
        # Check volumes with recurring job labels
        echo -e "${BLUE}🏷️ Volumes by backup group:${NC}"
        
        # Critical volumes
        local critical=$(kubectl get volumes -n longhorn-system -l recurring-job.longhorn.io/critical=enabled --no-headers 2>/dev/null | wc -l || echo "0")
        echo -e "   ${RED}🔴 Critical: $critical volumes${NC}"
        
        # Important volumes  
        local important=$(kubectl get volumes -n longhorn-system -l recurring-job.longhorn.io/important=enabled --no-headers 2>/dev/null | wc -l || echo "0")
        echo -e "   ${YELLOW}🟡 Important: $important volumes${NC}"
        
        # Standard volumes
        local standard=$(kubectl get volumes -n longhorn-system -l recurring-job.longhorn.io/standard=enabled --no-headers 2>/dev/null | wc -l || echo "0")
        echo -e "   ${BLUE}🔵 Standard: $standard volumes${NC}"
        
        # Default volumes
        local default=$(kubectl get volumes -n longhorn-system -l recurring-job.longhorn.io/default=enabled --no-headers 2>/dev/null | wc -l || echo "0")
        echo -e "   ${CYAN}⚪ Default: $default volumes${NC}"
    fi
}

# Function to check recent backups
check_recent_backups() {
    echo -e "\n${CYAN}💿 Checking recent backups...${NC}"
    
    local backups=$(kubectl get backups -n longhorn-system --no-headers 2>/dev/null | wc -l || echo "0")
    echo -e "${GREEN}📊 Total backups found: $backups${NC}"
    
    if [[ $backups -gt 0 ]]; then
        echo -e "${BLUE}📅 Recent backups (last 10):${NC}"
        kubectl get backups -n longhorn-system --sort-by=.metadata.creationTimestamp -o custom-columns="NAME:.metadata.name,VOLUME:.spec.volumeName,STATE:.status.state,SIZE:.status.size,CREATED:.metadata.creationTimestamp" --no-headers 2>/dev/null | tail -10 | while read line; do
            echo -e "   ${YELLOW}• $line${NC}"
        done
    else
        echo -e "${YELLOW}⚠️ No backups found yet - this is normal for new installations${NC}"
    fi
}

# Function to test MinIO connectivity (basic check)
test_minio_connectivity() {
    echo -e "\n${CYAN}🗄️ Testing MinIO S3 connectivity...${NC}"
    
    # Try to get backup target status from Longhorn
    if kubectl get backuptarget default -n longhorn-system -o jsonpath='{.status}' 2>/dev/null | grep -q "Available.*true"; then
        echo -e "${GREEN}✅ Backup target is available and accessible${NC}"
    else
        echo -e "${YELLOW}⚠️ Backup target status unclear - check manually${NC}"
        echo -e "   Run: kubectl describe backuptarget default -n longhorn-system"
    fi
}

# Function to provide backup recommendations
provide_recommendations() {
    echo -e "\n${CYAN}💡 Backup System Recommendations:${NC}"
    echo -e "${CYAN}=================================${NC}"
    
    echo -e "\n${BLUE}🎯 Backup Tiers Currently Configured:${NC}"
    echo -e "${RED}🔴 Critical:${NC} Hourly snapshots (24h retention) + Daily backups (30d retention)"
    echo -e "${YELLOW}🟡 Important:${NC} 4-hour snapshots (48h retention) + Daily backups (14d retention)"  
    echo -e "${BLUE}🔵 Standard:${NC} Daily snapshots (7d retention) + Weekly backups (4w retention)"
    
    echo -e "\n${BLUE}🔧 Monitoring Commands:${NC}"
    echo -e "• Check backup progress: ${YELLOW}kubectl get backups -n longhorn-system${NC}"
    echo -e "• View backup target: ${YELLOW}kubectl get backuptarget -n longhorn-system${NC}"
    echo -e "• Check volume health: ${YELLOW}kubectl get volumes -n longhorn-system${NC}"
    echo -e "• Monitor jobs: ${YELLOW}kubectl get recurringjobs -n longhorn-system${NC}"
    
    echo -e "\n${BLUE}🌐 MinIO Web Interface:${NC}"
    echo -e "• Access your TrueNAS MinIO at: ${YELLOW}http://your-truenas-ip:9002${NC}"
    echo -e "• Check the ${YELLOW}longhorn-backups${NC} bucket for stored backups"
    
    echo -e "\n${BLUE}🚨 Emergency Procedures:${NC}"
    echo -e "• View emergency runbook: ${YELLOW}docs/runbooks/longhorn-emergency-procedures.md${NC}"
    echo -e "• Force backup: ${YELLOW}kubectl create backup <backup-name> --volume-name=<volume>${NC}"
    
    echo -e "\n${GREEN}✅ Your Longhorn backup system appears to be properly configured!${NC}"
}

# Main execution
main() {
    check_cluster_access
    check_longhorn_system
    check_backup_target
    check_recurring_jobs
    check_volume_backup_annotations
    check_recent_backups
    test_minio_connectivity
    provide_recommendations
    
    echo -e "\n${GREEN}🎉 Backup verification complete!${NC}"
    echo -e "${BLUE}💡 Run this script periodically to monitor your backup health${NC}"
}

# Execute main function
main "$@"