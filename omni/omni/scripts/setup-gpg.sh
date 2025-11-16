#!/bin/bash
# ==============================================================================
# Omni GPG Encryption Key Setup Script
# ==============================================================================
# This script automates GPG key generation for Omni etcd encryption.
#
# The key will be used to encrypt etcd data at rest.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
OUTPUT_FILE="${PWD}/omni.asc"

# ==============================================================================
# Helper Functions
# ==============================================================================

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        print_error "$1 is not installed"
        return 1
    fi
}

# ==============================================================================
# Main Script
# ==============================================================================

echo "===================================="
echo "  Omni GPG Key Setup"
echo "===================================="
echo ""

# Check prerequisites
print_info "Checking prerequisites..."

if ! check_command "gpg"; then
    print_error "GPG is not installed. Please install gpg and try again."
    exit 1
fi

print_info "GPG version: $(gpg --version | head -1)"
echo ""

# Get email for key
print_info "This key will be used to encrypt Omni's etcd data."
print_warn "Use a real email address - you'll need it to manage the key later."
echo ""
read -p "Enter your email address: " USER_EMAIL

if [[ -z "$USER_EMAIL" ]]; then
    print_error "Email address is required"
    exit 1
fi

# Check if key already exists
if gpg --list-keys "$USER_EMAIL" &> /dev/null; then
    print_warn "A GPG key for $USER_EMAIL already exists!"
    read -p "Do you want to use the existing key? (y/n): " USE_EXISTING

    if [[ "$USE_EXISTING" =~ ^[Yy]$ ]]; then
        print_info "Using existing key..."
        EXISTING_KEY=true
    else
        print_error "Please remove existing key or use a different email"
        exit 1
    fi
fi

if [[ "${EXISTING_KEY:-false}" != "true" ]]; then
    # Generate primary key
    print_step "Step 1: Generating primary GPG key (RSA 4096)..."
    echo ""
    print_info "When prompted for a passphrase, press ENTER (no passphrase)"
    echo ""

    gpg --quick-generate-key \
        "Omni (Used for etcd data encryption) <$USER_EMAIL>" \
        rsa4096 \
        cert \
        never

    if [[ $? -ne 0 ]]; then
        print_error "Failed to generate primary key"
        exit 1
    fi

    print_info "Primary key generated successfully!"
fi

# Get key fingerprint
print_step "Step 2: Retrieving key fingerprint..."
KEY_FINGERPRINT=$(gpg --list-secret-keys --with-colons "$USER_EMAIL" | awk -F: '/^fpr:/ {print $10; exit}')

if [[ -z "$KEY_FINGERPRINT" ]]; then
    print_error "Failed to retrieve key fingerprint"
    exit 1
fi

print_info "Key fingerprint: $KEY_FINGERPRINT"

# Check if encryption subkey exists
if gpg --list-keys "$KEY_FINGERPRINT" | grep -q "\[E\]"; then
    print_info "Encryption subkey already exists"
else
    # Add encryption subkey
    print_step "Step 3: Adding encryption subkey..."
    echo ""
    print_info "When prompted for a passphrase, press ENTER (no passphrase)"
    echo ""

    gpg --quick-add-key "$KEY_FINGERPRINT" rsa4096 encr never

    if [[ $? -ne 0 ]]; then
        print_error "Failed to add encryption subkey"
        exit 1
    fi

    print_info "Encryption subkey added successfully!"
fi

# Display key information
print_step "Step 4: Verifying key configuration..."
echo ""
gpg -K --with-subkey-fingerprint "$USER_EMAIL"
echo ""

# Export the key
print_step "Step 5: Exporting key to file..."
gpg --export-secret-key --armor "$USER_EMAIL" > "$OUTPUT_FILE"

if [[ $? -eq 0 ]]; then
    print_info "Key exported successfully to: $OUTPUT_FILE"

    # Secure the exported key
    chmod 600 "$OUTPUT_FILE"

    print_info ""
    print_info "===================================="
    print_info "  Setup Complete!"
    print_info "===================================="
    print_info ""
    print_info "Key details:"
    print_info "  Email: $USER_EMAIL"
    print_info "  Fingerprint: $KEY_FINGERPRINT"
    print_info "  Exported to: $OUTPUT_FILE"
    print_info ""
    print_warn "IMPORTANT: Keep this key file secure!"
    print_warn "Without it, you cannot decrypt etcd data."
    print_warn ""
    print_info "Add this to your omni.env file:"
    echo "ETCD_ENCRYPTION_KEY=$(realpath "$OUTPUT_FILE")"
    print_info ""
    print_warn "Backup recommendations:"
    print_warn "  1. Copy $OUTPUT_FILE to secure backup location"
    print_warn "  2. Store passphrase securely (if you set one)"
    print_warn "  3. Consider storing fingerprint separately"
else
    print_error "Failed to export key"
    exit 1
fi

# Optional: Backup to additional location
echo ""
read -p "Do you want to backup the key to another location? (y/n): " BACKUP_KEY

if [[ "$BACKUP_KEY" =~ ^[Yy]$ ]]; then
    read -p "Enter backup path: " BACKUP_PATH

    if [[ -n "$BACKUP_PATH" ]]; then
        mkdir -p "$(dirname "$BACKUP_PATH")"
        cp "$OUTPUT_FILE" "$BACKUP_PATH"
        chmod 600 "$BACKUP_PATH"
        print_info "Key backed up to: $BACKUP_PATH"
    fi
fi

print_info ""
print_info "You can now proceed with Omni deployment!"
