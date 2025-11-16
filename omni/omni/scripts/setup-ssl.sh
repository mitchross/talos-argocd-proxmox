#!/bin/bash
# ==============================================================================
# Omni SSL Certificate Setup Script (Cloudflare DNS)
# ==============================================================================
# This script automates SSL certificate generation using Certbot with Cloudflare
# DNS validation for Omni deployment.
#
# Prerequisites:
# - Certbot installed
# - Domain hosted on Cloudflare
# - Cloudflare API token with DNS:Edit permissions

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUDFLARE_CREDS_FILE="${HOME}/omni/cloudflare.ini"

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
echo "  Omni SSL Certificate Setup"
echo "===================================="
echo ""

# Check if running as root for certbot
if [[ $EUID -ne 0 ]]; then
   print_warn "This script should be run as root (or with sudo) for Certbot operations"
   print_info "Re-running with sudo..."
   sudo "$0" "$@"
   exit $?
fi

# Check prerequisites
print_info "Checking prerequisites..."

if ! check_command "certbot"; then
    print_error "Certbot not found. Installing..."
    snap install --classic certbot
    ln -s /snap/bin/certbot /usr/bin/certbot
fi

# Check for Cloudflare plugin
if ! snap list | grep -q "certbot-dns-cloudflare"; then
    print_info "Installing Cloudflare DNS plugin..."
    snap set certbot trust-plugin-with-root=ok
    snap install certbot-dns-cloudflare
fi

# Get domain name
read -p "Enter your Omni domain name (e.g., omni.example.com): " DOMAIN_NAME

if [[ -z "$DOMAIN_NAME" ]]; then
    print_error "Domain name is required"
    exit 1
fi

print_info "Domain: $DOMAIN_NAME"

# Get Cloudflare API token
read -sp "Enter your Cloudflare API token: " CF_API_TOKEN
echo ""

if [[ -z "$CF_API_TOKEN" ]]; then
    print_error "Cloudflare API token is required"
    exit 1
fi

# Create credentials file
print_info "Creating Cloudflare credentials file..."
mkdir -p "$(dirname "$CLOUDFLARE_CREDS_FILE")"
cat > "$CLOUDFLARE_CREDS_FILE" <<EOF
# Cloudflare API token for DNS validation
dns_cloudflare_api_token = $CF_API_TOKEN
EOF

chmod 600 "$CLOUDFLARE_CREDS_FILE"
print_info "Credentials saved to: $CLOUDFLARE_CREDS_FILE"

# Generate certificate
print_info "Requesting SSL certificate from Let's Encrypt..."
certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials "$CLOUDFLARE_CREDS_FILE" \
    -d "$DOMAIN_NAME" \
    --non-interactive \
    --agree-tos \
    --email "${SUDO_USER}@${DOMAIN_NAME}"

if [[ $? -eq 0 ]]; then
    print_info "Certificate generated successfully!"
    print_info ""
    print_info "Certificate files location:"
    print_info "  - Certificate: /etc/letsencrypt/live/${DOMAIN_NAME}/fullchain.pem"
    print_info "  - Private Key: /etc/letsencrypt/live/${DOMAIN_NAME}/privkey.pem"
    print_info ""
    print_info "Add these to your omni.env file:"
    echo "TLS_CERT=/etc/letsencrypt/live/${DOMAIN_NAME}/fullchain.pem"
    echo "TLS_KEY=/etc/letsencrypt/live/${DOMAIN_NAME}/privkey.pem"
else
    print_error "Certificate generation failed"
    exit 1
fi

# Setup auto-renewal
print_info "Setting up automatic certificate renewal..."
systemctl enable certbot.timer
systemctl start certbot.timer

print_info ""
print_info "Setup complete! Certificate will auto-renew before expiration."
print_warn "Remember to restart Omni after certificate renewal: docker compose restart omni"
