#!/bin/sh
# ==============================================================================
# Certbot deploy hook: restart Omni after a certificate renewal
# ==============================================================================
# Omni reads the TLS cert only at startup, so a renewed cert does nothing until
# the container is recreated.
#
# Install with:
#   sudo install -m 755 restart-omni-after-renewal.sh \
#     /etc/letsencrypt/renewal-hooks/deploy/restart-omni-after-renewal.sh
#
# Verify the whole chain works before you depend on it:
#   sudo certbot renew --dry-run
#
# EDIT THESE TWO VALUES for your deployment.
# ==============================================================================

set -eu

DOMAIN_NAME="omni.example.com"
COMPOSE_DIR="/path/to/omni"

SERVICE_NAME="omni"

# Certbot sets RENEWED_LINEAGE for each renewed cert. Bail out for any other
# domain so this hook does not restart Omni when unrelated certs renew.
DOMAIN="${RENEWED_LINEAGE##*/}"

if [ "$DOMAIN" != "$DOMAIN_NAME" ]; then
    exit 0
fi

# --env-file is required: docker-compose.yml interpolates ${VARS} from omni.env.
# Without it Compose substitutes empty strings and fails ("invalid spec: :/_out/etcd").
#
# Use `up -d --force-recreate` rather than `restart`: the renewed cert is a new
# inode behind the live/ symlink, and a plain restart may keep the stale one.
/usr/bin/docker compose \
    -f "$COMPOSE_DIR/docker-compose.yml" \
    --project-directory "$COMPOSE_DIR" \
    --env-file "$COMPOSE_DIR/omni.env" \
    up -d --force-recreate "$SERVICE_NAME"
