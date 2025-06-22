#!/bin/bash
# Longhorn Backup Management Script
# Comprehensive backup, snapshot, and disaster recovery operations

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
LONGHORN_NAMESPACE="longhorn-system"
BACKUP_TARGET_NFS="nfs://TRUENAS_IP:/mnt/pool/longhorn-backups"
BACKUP_TARGET_S3="s3://longhorn-backups@us-east-1/"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Longhorn is installed
check_longhorn() {
    if ! kubectl get namespace "$LONGHORN_NAMESPACE" >/dev/null 2>&1; then
        log_error "Longhorn namespace not found. Is Longhorn installed?"
        exit 1
    fi
    log_success "Longhorn found in namespace: $LONGHORN_NAMESPACE"
}

# Configure backup target
configure_backup_target() {
    local target_type="$1"
    local target_url=""
    
    case "$target_type" in
        "nfs")
            read -p "Enter TrueNAS IP address: " truenas_ip
            read -p "Enter NFS path (default: /mnt/pool/longhorn-backups): " nfs_path
            nfs_path=${nfs_path:-/mnt/pool/longhorn-backups}
            target_url="nfs://${truenas_ip}:${nfs_path}"
            ;;
        "s3")
            read -p "Enter S3 endpoint (TrueNAS MinIO): " s3_endpoint
            read -p "Enter bucket name: " bucket_name
            read -p "Enter region (default: us-east-1): " region
            region=${region:-us-east-1}
            target_url="s3://${bucket_name}@${region}/"
            
            # Configure S3 credentials
            read -p "Enter Access Key ID: " access_key
            read -s -p "Enter Secret Access Key: " secret_key
            echo
            
            kubectl create secret generic longhorn-backup-credentials \
                --from-literal=AWS_ACCESS_KEY_ID="$access_key" \
                --from-literal=AWS_SECRET_ACCESS_KEY="$secret_key" \
                --from-literal=AWS_ENDPOINTS="$s3_endpoint" \
                -n "$LONGHORN_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
            ;;
        *)
            log_error "Invalid backup target type. Use 'nfs' or 's3'"
            exit 1
            ;;
    esac
    
    # Apply backup target setting
    kubectl patch setting backup-target -n "$LONGHORN_NAMESPACE" --type='merge' -p="{\"spec\":{\"value\":\"$target_url\"}}" 2>/dev/null || \
    kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Setting
metadata:
  name: backup-target
  namespace: $LONGHORN_NAMESPACE
spec:
  value: "$target_url"
EOF
    
    log_success "Backup target configured: $target_url"
}

# List all volumes
list_volumes() {
    log_info "Listing all Longhorn volumes..."
    kubectl get volumes -n "$LONGHORN_NAMESPACE" -o custom-columns="NAME:.metadata.name,SIZE:.spec.size,STATE:.status.state,ROBUSTNESS:.status.robustness,PVC:.status.kubernetesStatus.pvcName,NAMESPACE:.status.kubernetesStatus.namespace"
}

# Create manual snapshot
create_snapshot() {
    local volume_name="$1"
    local snapshot_name="${volume_name}-manual-$(date +%Y%m%d-%H%M%S)"
    
    log_info "Creating snapshot for volume: $volume_name"
    
    kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: $snapshot_name
  namespace: $LONGHORN_NAMESPACE
spec:
  volume: $volume_name
  labels:
    type: manual
    created-by: backup-script
EOF
    
    log_success "Snapshot created: $snapshot_name"
}

# Create manual backup
create_backup() {
    local volume_name="$1"
    local backup_name="${volume_name}-backup-$(date +%Y%m%d-%H%M%S)"
    
    log_info "Creating backup for volume: $volume_name"
    
    kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Backup
metadata:
  name: $backup_name
  namespace: $LONGHORN_NAMESPACE
spec:
  volume: $volume_name
  labels:
    type: manual
    created-by: backup-script
EOF
    
    log_success "Backup initiated: $backup_name"
    log_info "Monitor progress with: kubectl get backup $backup_name -n $LONGHORN_NAMESPACE -w"
}

# List snapshots for a volume
list_snapshots() {
    local volume_name="$1"
    
    log_info "Listing snapshots for volume: $volume_name"
    kubectl get snapshots -n "$LONGHORN_NAMESPACE" -l "longhornvolume=$volume_name" -o custom-columns="NAME:.metadata.name,CREATED:.metadata.creationTimestamp,SIZE:.status.size,READY:.status.readyToUse"
}

# List backups for a volume
list_backups() {
    local volume_name="$1"
    
    log_info "Listing backups for volume: $volume_name"
    kubectl get backups -n "$LONGHORN_NAMESPACE" -l "longhornvolume=$volume_name" -o custom-columns="NAME:.metadata.name,CREATED:.metadata.creationTimestamp,STATE:.status.state,PROGRESS:.status.progress"
}

# Restore from backup
restore_from_backup() {
    local backup_name="$1"
    local new_volume_name="$2"
    
    log_info "Restoring backup $backup_name to new volume: $new_volume_name"
    
    kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: $new_volume_name
  namespace: $LONGHORN_NAMESPACE
spec:
  fromBackup: $backup_name
  numberOfReplicas: 3
  size: "20Gi"  # Adjust as needed
EOF
    
    log_success "Restore initiated. New volume: $new_volume_name"
    log_info "Monitor progress with: kubectl get volume $new_volume_name -n $LONGHORN_NAMESPACE -w"
}

# Disaster recovery - backup all critical volumes
disaster_recovery_backup() {
    log_info "Starting disaster recovery backup for all critical volumes..."
    
    # Get all volumes with critical label or in specific namespaces
    local critical_volumes=$(kubectl get volumes -n "$LONGHORN_NAMESPACE" -o jsonpath='{.items[?(@.metadata.labels.data-tier=="critical")].metadata.name}')
    
    if [ -z "$critical_volumes" ]; then
        log_warning "No critical volumes found. Backing up all volumes..."
        critical_volumes=$(kubectl get volumes -n "$LONGHORN_NAMESPACE" -o jsonpath='{.items[*].metadata.name}')
    fi
    
    for volume in $critical_volumes; do
        log_info "Creating disaster recovery backup for: $volume"
        create_backup "$volume"
        sleep 5  # Prevent overwhelming the system
    done
    
    log_success "Disaster recovery backup initiated for all critical volumes"
}

# Cleanup old snapshots and backups
cleanup_old_backups() {
    local days_to_keep="${1:-30}"
    
    log_info "Cleaning up snapshots and backups older than $days_to_keep days..."
    
    # This would typically be done through Longhorn's recurring job retention
    # But we can also manually clean up
    local cutoff_date=$(date -d "$days_to_keep days ago" +%Y-%m-%dT%H:%M:%SZ)
    
    log_warning "Manual cleanup not implemented - use Longhorn UI or recurring job retention"
    log_info "Cutoff date would be: $cutoff_date"
}

# Check backup health
check_backup_health() {
    log_info "Checking backup system health..."
    
    # Check backup target connectivity
    local backup_target=$(kubectl get setting backup-target -n "$LONGHORN_NAMESPACE" -o jsonpath='{.spec.value}')
    
    if [ -z "$backup_target" ]; then
        log_error "No backup target configured"
        return 1
    fi
    
    log_info "Backup target: $backup_target"
    
    # Check recent backup jobs
    local recent_backups=$(kubectl get backups -n "$LONGHORN_NAMESPACE" --sort-by=.metadata.creationTimestamp | tail -5)
    
    if [ -z "$recent_backups" ]; then
        log_warning "No recent backups found"
    else
        log_success "Recent backups found"
        echo "$recent_backups"
    fi
    
    # Check recurring jobs
    local recurring_jobs=$(kubectl get recurringjobs -n "$LONGHORN_NAMESPACE" -o custom-columns="NAME:.metadata.name,CRON:.spec.cron,TASK:.spec.task,GROUPS:.spec.groups")
    
    if [ -z "$recurring_jobs" ]; then
        log_warning "No recurring jobs configured"
    else
        log_success "Recurring jobs configured:"
        echo "$recurring_jobs"
    fi
}

# Apply data tier labels to volumes based on PVC namespaces
label_volumes_by_tier() {
    log_info "Applying data tier labels to volumes..."
    
    # Critical: databases, user data
    local critical_namespaces="cloudnative-pg immich khoj paperless-ngx"
    
    # Important: media, configs, home automation
    local important_namespaces="frigate jellyfin plex home-assistant hoarder"
    
    # Standard: everything else
    for ns in $critical_namespaces; do
        kubectl get volumes -n "$LONGHORN_NAMESPACE" -o json | jq -r ".items[] | select(.status.kubernetesStatus.namespace==\"$ns\") | .metadata.name" | while read volume; do
            kubectl label volume "$volume" -n "$LONGHORN_NAMESPACE" data-tier=critical --overwrite
            log_success "Labeled $volume as critical"
        done
    done
    
    for ns in $important_namespaces; do
        kubectl get volumes -n "$LONGHORN_NAMESPACE" -o json | jq -r ".items[] | select(.status.kubernetesStatus.namespace==\"$ns\") | .metadata.name" | while read volume; do
            kubectl label volume "$volume" -n "$LONGHORN_NAMESPACE" data-tier=important --overwrite
            log_success "Labeled $volume as important"
        done
    done
}

# Main menu
show_menu() {
    echo
    echo "🗄️  Longhorn Backup Management"
    echo "================================"
    echo "1.  Configure backup target (NFS/S3)"
    echo "2.  List all volumes"
    echo "3.  Create manual snapshot"
    echo "4.  Create manual backup"
    echo "5.  List snapshots for volume"
    echo "6.  List backups for volume"
    echo "7.  Restore from backup"
    echo "8.  Disaster recovery backup (all critical)"
    echo "9.  Check backup system health"
    echo "10. Label volumes by data tier"
    echo "11. Cleanup old backups"
    echo "0.  Exit"
    echo
}

# Main execution
main() {
    check_longhorn
    
    while true; do
        show_menu
        read -p "Select an option: " choice
        
        case $choice in
            1)
                echo "Select backup target type:"
                echo "1. NFS (TrueNAS Scale)"
                echo "2. S3 (TrueNAS MinIO)"
                read -p "Choice: " target_choice
                case $target_choice in
                    1) configure_backup_target "nfs" ;;
                    2) configure_backup_target "s3" ;;
                    *) log_error "Invalid choice" ;;
                esac
                ;;
            2) list_volumes ;;
            3)
                read -p "Enter volume name: " volume_name
                create_snapshot "$volume_name"
                ;;
            4)
                read -p "Enter volume name: " volume_name
                create_backup "$volume_name"
                ;;
            5)
                read -p "Enter volume name: " volume_name
                list_snapshots "$volume_name"
                ;;
            6)
                read -p "Enter volume name: " volume_name
                list_backups "$volume_name"
                ;;
            7)
                read -p "Enter backup name: " backup_name
                read -p "Enter new volume name: " new_volume_name
                restore_from_backup "$backup_name" "$new_volume_name"
                ;;
            8) disaster_recovery_backup ;;
            9) check_backup_health ;;
            10) label_volumes_by_tier ;;
            11)
                read -p "Enter days to keep (default 30): " days
                cleanup_old_backups "${days:-30}"
                ;;
            0) 
                log_info "Exiting..."
                exit 0
                ;;
            *) log_error "Invalid option" ;;
        esac
        
        echo
        read -p "Press Enter to continue..."
    done
}

# Run main function
main "$@" 