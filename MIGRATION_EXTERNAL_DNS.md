# Migration to ExternalDNS-Based Split DNS Architecture

## Summary

This migration implements automatic DNS management for external services while keeping internal services completely off Cloudflare, improving security and reducing manual DNS management.

## What Changed

### Before
- Manual CNAME records in Cloudflare for each service
- Wildcard DNS `*.vanillax.me` pointed to Cloudflare Tunnel
- No clear separation between internal and external services
- Manual DNS updates required for new services

### After
- **ExternalDNS automatically manages** Cloudflare DNS for external services
- **Internal services have NO Cloudflare DNS** - completely private
- **Annotation-based routing** - add annotation to make service public
- **Security by default** - services are internal unless explicitly marked external

## Changes Made

### 1. New Components Added

```
infrastructure/controllers/external-dns/
├── values.yaml                        # ExternalDNS Helm configuration
├── cloudflare-external-secret.yaml    # Cloudflare API token from 1Password
├── kustomization.yaml                 # Kustomize config
├── ns.yaml                            # Namespace
└── README.md                          # Detailed documentation

infrastructure/controllers/argocd/apps/
└── external-dns-app.yaml              # ArgoCD Application for ExternalDNS

infrastructure/networking/cloudflared/
└── config-explicit.yaml.example       # Optional explicit tunnel config
```

### 2. Updated HTTPRoutes (6 external services)

Added ExternalDNS annotation to:
- `my-apps/privacy/searxng/httproute.yaml`
- `my-apps/privacy/proxitok/httproute.yaml`
- `my-apps/media/libreddit/httproute.yaml`
- `my-apps/media/karakeep/karakeep/httproute.yaml`
- `my-apps/development/vert/httproute.yaml`
- `my-apps/development/it-tools/httproute.yaml`

### 3. Updated Cloudflare Tunnel Config

Added security comments explaining the wildcard approach in:
- `infrastructure/networking/cloudflared/config.yaml`

## Action Required

### CRITICAL: Replace TUNNEL_ID Placeholder

**You MUST replace `TUNNEL_ID` with your actual Cloudflare Tunnel ID** in all HTTPRoute files.

#### Find Your Tunnel ID

**Option 1: Cloudflare Dashboard**
1. Go to: https://one.dash.cloudflare.com/
2. Navigate to: Networks → Tunnels
3. Click on your "threadripper" tunnel
4. Copy the Tunnel ID (format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

**Option 2: Check Existing DNS Records**
1. Go to Cloudflare DNS for `vanillax.me`
2. Look at any existing CNAME record (like `search.vanillax.me`)
3. The CNAME target should be `<tunnel-id>.cfargotunnel.com`
4. Copy everything before `.cfargotunnel.com`

**Option 3: CLI (if you have cloudflared installed locally)**
```bash
cloudflared tunnel list | grep threadripper
```

#### Update All HTTPRoutes

Once you have your tunnel ID, run:

```bash
# Replace YOUR_TUNNEL_ID_HERE with your actual tunnel ID
export TUNNEL_ID="YOUR_TUNNEL_ID_HERE"

# Update all HTTPRoutes
cd /path/to/talos-argocd-proxmox
find my-apps -name httproute.yaml -exec grep -l "TUNNEL_ID" {} \; | while read file; do
  echo "Updating $file"
  sed -i "s/TUNNEL_ID/$TUNNEL_ID/g" "$file"
done

# Verify changes
grep -r "external-dns.alpha.kubernetes.io/target" my-apps/*/httproute.yaml
```

## Deployment Steps

### 1. Update Tunnel ID (REQUIRED)
Follow instructions above to replace `TUNNEL_ID` with your actual tunnel ID.

### 2. Commit and Push
```bash
git add .
git commit -m "Add ExternalDNS for automated Cloudflare DNS management

- Deploy ExternalDNS controller for Cloudflare
- Add annotations to 6 external HTTPRoutes
- Keep 20+ internal services completely off Cloudflare
- Improve security with annotation-based public access control"

git push -u origin claude/review-ingress-cloudflare-01YXCQ2nRE1sVQThEBBmpQjg
```

### 3. Verify ArgoCD Syncs ExternalDNS
```bash
# Wait for ArgoCD to sync
kubectl get application -n argocd external-dns -w

# Check ExternalDNS pod is running
kubectl get pods -n external-dns

# Watch ExternalDNS create DNS records
kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns -f
```

### 4. Verify DNS Records Created
```bash
# Check each external service resolves
dig search.vanillax.me @1.1.1.1
dig proxitok.vanillax.me @1.1.1.1
dig libreddit.vanillax.me @1.1.1.1
dig karakeep.vanillax.me @1.1.1.1
dig vert.vanillax.me @1.1.1.1
dig it-tools.vanillax.me @1.1.1.1

# All should return CNAME pointing to your tunnel
```

### 5. Test Services Still Work
```bash
# Test each external service from internet (not LAN)
curl -I https://search.vanillax.me
curl -I https://proxitok.vanillax.me
# etc...
```

### 6. Clean Up Manual DNS Records (Optional)

Once ExternalDNS is working and you've verified all services are accessible:

1. Go to Cloudflare DNS for `vanillax.me`
2. Delete the old manual CNAME records for:
   - search.vanillax.me
   - proxitok.vanillax.me
   - libreddit.vanillax.me
   - karakeep.vanillax.me
   - vert.vanillax.me
   - it-tools.vanillax.me

ExternalDNS will recreate them automatically with proper ownership tracking (TXT records).

## Service Inventory

### External Services (6) - Will be in Cloudflare DNS
✅ search.vanillax.me (searxng)
✅ proxitok.vanillax.me
✅ libreddit.vanillax.me
✅ karakeep.vanillax.me
✅ vert.vanillax.me
✅ it-tools.vanillax.me

### Internal Services (20+) - Will NOT be in Cloudflare DNS
🔒 immich.vanillax.me
🔒 jellyfin.vanillax.me
🔒 home-assistant.vanillax.me
🔒 frigate.vanillax.me
🔒 gitea.vanillax.me
🔒 n8n.vanillax.me
🔒 ollama.vanillax.me
🔒 ollama-webui.vanillax.me
🔒 ... and 12+ more

These remain LAN-only and never touch Cloudflare.

## Rollback Plan

If something goes wrong:

### Quick Rollback
```bash
# Disable ExternalDNS
kubectl scale deployment -n external-dns external-dns --replicas=0

# Manually recreate DNS records in Cloudflare if needed
```

### Full Rollback
```bash
# Remove ArgoCD application
kubectl delete application -n argocd external-dns

# Remove namespace
kubectl delete namespace external-dns

# Revert git changes
git revert HEAD
git push
```

## Future: Adding New Services

### Make a Service Public
```yaml
annotations:
  external-dns.alpha.kubernetes.io/target: "<tunnel-id>.cfargotunnel.com"
spec:
  parentRefs:
    - name: gateway-external
```

### Keep a Service Private (Default)
```yaml
# No external-dns annotation
spec:
  parentRefs:
    - name: gateway-internal
```

## Security Improvements

✅ **Reduced Attack Surface**: Only 6 services exposed publicly instead of wildcard
✅ **Zero Trust**: Internal services never advertised to Cloudflare
✅ **Audit Trail**: Easy to see which services are public (grep for annotation)
✅ **Automation**: No manual DNS changes = fewer mistakes
✅ **GitOps**: DNS changes are code-reviewed and version controlled

## Questions?

See detailed documentation:
- `infrastructure/controllers/external-dns/README.md`
- ExternalDNS docs: https://kubernetes-sigs.github.io/external-dns/
- Gateway API docs: https://gateway-api.sigs.k8s.io/

## Validation Checklist

Before considering migration complete:

- [ ] TUNNEL_ID replaced with actual tunnel ID in all 6 HTTPRoutes
- [ ] Committed and pushed changes
- [ ] ArgoCD synced external-dns Application
- [ ] ExternalDNS pod is Running
- [ ] DNS records created in Cloudflare (check with `dig`)
- [ ] All 6 external services accessible from internet
- [ ] Internal services still accessible from LAN
- [ ] Internal services NOT in Cloudflare DNS
- [ ] Old manual DNS records removed (optional)
