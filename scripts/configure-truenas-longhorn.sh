#!/bin/bash
# TrueNAS Scale Configuration for Longhorn Backups
# Based on your existing setup: /mnt/BigTank/k8s/longhornbackup

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration based on your TrueNAS setup
TRUENAS_IP="192.168.10.139"  # Update this to your TrueNAS IP
NFS_PATH="/mnt/BigTank/k8s/longhornbackup"
BACKUP_TARGET="nfs://${TRUENAS_IP}:${NFS_PATH}"

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

# Test NFS connectivity
test_nfs_connectivity() {
    log_info "Testing NFS connectivity to TrueNAS..."
    
    # Create test mount point
    sudo mkdir -p /tmp/longhorn-test
    
    # Test mount
    if sudo mount -t nfs "${TRUENAS_IP}:${NFS_PATH}" /tmp/longhorn-test; then
        log_success "NFS mount successful!"
        
        # Test write permissions
        if sudo touch /tmp/longhorn-test/test-file 2>/dev/null; then
            log_success "Write permissions confirmed"
            sudo rm /tmp/longhorn-test/test-file
        else
            log_error "No write permissions - check NFS share settings"
            sudo umount /tmp/longhorn-test
            return 1
        fi
        
        # Unmount
        sudo umount /tmp/longhorn-test
        sudo rmdir /tmp/longhorn-test
        
        return 0
    else
        log_error "NFS mount failed - check network connectivity and NFS service"
        sudo rmdir /tmp/longhorn-test 2>/dev/null || true
        return 1
    fi
}

# Configure Longhorn backup target
configure_longhorn_backup() {
    log_info "Configuring Longhorn backup target..."
    
    # Check if Longhorn is installed
    if ! kubectl get namespace longhorn-system >/dev/null 2>&1; then
        log_error "Longhorn namespace not found. Is Longhorn installed?"
        return 1
    fi
    
    # Apply backup target setting
    log_info "Setting backup target to: $BACKUP_TARGET"
    
    kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Setting
metadata:
  name: backup-target
  namespace: longhorn-system
spec:
  value: "$BACKUP_TARGET"
EOF
    
    log_success "Longhorn backup target configured"
}

# Verify backup configuration
verify_backup_config() {
    log_info "Verifying backup configuration..."
    
    # Check backup target setting
    local backup_target=$(kubectl get setting backup-target -n longhorn-system -o jsonpath='{.spec.value}' 2>/dev/null || echo "")
    
    if [ "$backup_target" = "$BACKUP_TARGET" ]; then
        log_success "Backup target correctly set to: $backup_target"
    else
        log_error "Backup target mismatch. Expected: $BACKUP_TARGET, Got: $backup_target"
        return 1
    fi
    
    # Check if backup target is available
    log_info "Checking backup target availability..."
    sleep 5  # Give Longhorn time to detect the target
    
    # This will be available once Longhorn tests the connection
    log_info "Backup target configured. Check Longhorn UI for connectivity status."
}

# Apply backup settings and recurring jobs
apply_backup_configuration() {
    log_info "Applying Longhorn backup configuration..."
    
    # Apply backup settings
    if kubectl apply -f infrastructure/storage/longhorn/backup-settings.yaml; then
        log_success "Backup settings applied"
    else
        log_error "Failed to apply backup settings"
        return 1
    fi
    
    # Apply recurring jobs
    if kubectl apply -f infrastructure/storage/longhorn/recurring-jobs.yaml; then
        log_success "Recurring jobs applied"
    else
        log_error "Failed to apply recurring jobs"
        return 1
    fi
}

# Show TrueNAS configuration instructions
show_truenas_instructions() {
    echo
    echo "🏠 TrueNAS Scale Configuration Instructions"
    echo "=========================================="
    echo
    echo "Based on your existing setup, verify these NFS share settings:"
    echo
    echo "1. Go to Sharing → Unix (NFS) Shares"
    echo "2. Edit your 'longhornbackup' share and ensure:"
    echo "   📁 Path: /mnt/BigTank/k8s/longhornbackup"
    echo "   🌐 Networks: 192.168.10.0/24 (or your K8s subnet)"
    echo "   👤 Maproot User: root"
    echo "   👥 Maproot Group: wheel"
    echo "   🔒 Security: NFSv3/NFSv4 enabled"
    echo
    echo "3. Optional: Enable ZFS auto-snapshots for additional protection:"
    echo "   zfs set com.sun:auto-snapshot=true BigTank/k8s/longhornbackup"
    echo "   zfs set com.sun:auto-snapshot:hourly=48 BigTank/k8s/longhornbackup"
    echo "   zfs set com.sun:auto-snapshot:daily=30 BigTank/k8s/longhornbackup"
    echo
}

# Main execution
main() {
    echo "🗄️ TrueNAS Scale + Longhorn Backup Configuration"
    echo "==============================================="
    echo
    echo "TrueNAS IP: $TRUENAS_IP"
    echo "NFS Path: $NFS_PATH"
    echo "Backup Target: $BACKUP_TARGET"
    echo
    
    # Show TrueNAS instructions first
    show_truenas_instructions
    
    read -p "Have you verified the NFS share settings above? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_warning "Please configure TrueNAS NFS share settings first, then run this script again"
        exit 0
    fi
    
    # Test NFS connectivity
    if ! test_nfs_connectivity; then
        log_error "NFS connectivity test failed. Please check TrueNAS configuration."
        exit 1
    fi
    
    # Configure Longhorn
    if ! configure_longhorn_backup; then
        log_error "Failed to configure Longhorn backup target"
        exit 1
    fi
    
    # Apply backup configuration
    if ! apply_backup_configuration; then
        log_error "Failed to apply backup configuration"
        exit 1
    fi
    
    # Verify configuration
    if ! verify_backup_config; then
        log_error "Backup configuration verification failed"
        exit 1
    fi
    
    echo
    log_success "✅ TrueNAS + Longhorn backup configuration complete!"
    echo
    echo "Next steps:"
    echo "1. Check Longhorn UI for backup target connectivity"
    echo "2. Run: ./scripts/longhorn-backup-management.sh"
    echo "3. Select option 10 to label volumes by data tier"
    echo "4. Select option 9 to check backup system health"
    echo "5. Create a test backup with option 4"
    echo
}

# Run main function
main "$@" 