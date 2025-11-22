# ExternalDNS for Cloudflare - Split DNS Architecture

This directory contains the configuration for ExternalDNS to automatically manage Cloudflare DNS records for external services only, while keeping internal services completely private.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Cloudflare DNS (Public)                                          │
│                                                                   │
│ ONLY External Services:                                          │
│ ├─ search.vanillax.me     → TUNNEL_ID.cfargotunnel.com          │
│ ├─ proxitok.vanillax.me   → TUNNEL_ID.cfargotunnel.com          │
│ ├─ libreddit.vanillax.me  → TUNNEL_ID.cfargotunnel.com          │
│ ├─ karakeep.vanillax.me   → TUNNEL_ID.cfargotunnel.com          │
│ ├─ vert.vanillax.me       → TUNNEL_ID.cfargotunnel.com          │
│ └─ it-tools.vanillax.me   → TUNNEL_ID.cfargotunnel.com          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Cloudflare Tunnel (threadripper)                                 │
│ └─ Wildcard: *.vanillax.me → Cilium Gateway External            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Kubernetes Cluster                                                │
│                                                                   │
│ Gateway External (192.168.10.49)                                 │
│ ├─ HTTPRoute: search.vanillax.me    → searxng                   │
│ ├─ HTTPRoute: proxitok.vanillax.me  → proxitok                  │
│ ├─ HTTPRoute: libreddit.vanillax.me → libreddit                 │
│ ├─ HTTPRoute: karakeep.vanillax.me  → karakeep                  │
│ ├─ HTTPRoute: vert.vanillax.me      → vert                      │
│ └─ HTTPRoute: it-tools.vanillax.me  → it-tools                  │
│                                                                   │
│ Gateway Internal (192.168.10.50) - NO CLOUDFLARE DNS            │
│ ├─ HTTPRoute: immich.vanillax.me         → immich   (LAN ONLY)  │
│ ├─ HTTPRoute: jellyfin.vanillax.me       → jellyfin (LAN ONLY)  │
│ ├─ HTTPRoute: home-assistant.vanillax.me → hass     (LAN ONLY)  │
│ ├─ HTTPRoute: gitea.vanillax.me          → gitea    (LAN ONLY)  │
│ └─ ... 16+ more internal services ...                            │
└─────────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. **ExternalDNS watches HTTPRoutes**
   - Only processes HTTPRoutes with the annotation: `external-dns.alpha.kubernetes.io/target`
   - Creates CNAME records in Cloudflare pointing to your tunnel
   - Automatically updates/removes records when HTTPRoutes change

### 2. **Security by Default**
   - **Internal services** (gateway-internal): NO annotation → NO DNS record → NOT accessible from internet
   - **External services** (gateway-external): Has annotation → DNS record created → Accessible via Cloudflare

### 3. **Split-Horizon DNS**
   - **From Internet**: Only external services resolve via Cloudflare DNS
   - **From LAN**: All services can resolve via local DNS (CoreDNS, Pi-hole, etc.)

## Setup Instructions

### Step 1: Get Your Cloudflare Tunnel ID

Your tunnel name is `threadripper`. You need to find its tunnel ID:

**Option A: From Cloudflare Dashboard**
1. Go to Cloudflare Zero Trust → Networks → Tunnels
2. Click on "threadripper" tunnel
3. Find the tunnel ID (format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
4. Your CNAME target is: `<tunnel-id>.cfargotunnel.com`

**Option B: From existing DNS records**
1. Check your existing CNAME records in Cloudflare DNS
2. Look for any record pointing to `*.cfargotunnel.com`
3. Copy that full CNAME target

### Step 2: Update HTTPRoute Annotations

Replace `TUNNEL_ID` with your actual tunnel ID in these files:
```bash
# All 6 external HTTPRoutes have been updated with placeholder
# Search and replace TUNNEL_ID with your actual tunnel ID

find my-apps -name httproute.yaml -exec grep -l "TUNNEL_ID" {} \; | while read file; do
  sed -i 's/TUNNEL_ID/<your-actual-tunnel-id>/g' "$file"
done
```

Or manually update:
- `my-apps/privacy/searxng/httproute.yaml`
- `my-apps/privacy/proxitok/httproute.yaml`
- `my-apps/media/libreddit/httproute.yaml`
- `my-apps/media/karakeep/karakeep/httproute.yaml`
- `my-apps/development/vert/httproute.yaml`
- `my-apps/development/it-tools/httproute.yaml`

### Step 3: Ensure ArgoCD App is Deployed

The ArgoCD Application is at:
```
infrastructure/controllers/argocd/apps/external-dns-app.yaml
```

Make sure this file is referenced in your main ArgoCD Applications list.

### Step 4: Remove Manual DNS Records

Once ExternalDNS is deployed and working, you can remove these manual CNAME records from Cloudflare:
- ❌ convert.vanillax.me
- ❌ it-tools.vanillax.me
- ❌ karakeep.vanillax.me
- ❌ libreddit.vanillax.me
- ❌ photos.vanillax.me
- ❌ proxitok.vanillax.me
- ❌ search.vanillax.me

ExternalDNS will recreate them automatically (without the "convert" and "photos" if they don't have corresponding HTTPRoutes).

### Step 5: Monitor ExternalDNS

```bash
# Watch ExternalDNS logs
kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns -f

# Check created DNS records
kubectl get httproute -A -o custom-columns=\
NAME:.metadata.name,\
NAMESPACE:.metadata.namespace,\
HOSTNAME:.spec.hostnames[0],\
ANNOTATION:.metadata.annotations.external-dns\.alpha\.kubernetes\.io/target
```

## Adding New External Services

To make a new service accessible from the internet:

1. **Deploy your service** with an HTTPRoute using `gateway-external`
2. **Add the annotation** to the HTTPRoute:
   ```yaml
   apiVersion: gateway.networking.k8s.io/v1
   kind: HTTPRoute
   metadata:
     name: my-new-service
     namespace: my-namespace
     annotations:
       external-dns.alpha.kubernetes.io/target: "<tunnel-id>.cfargotunnel.com"
   spec:
     parentRefs:
       - name: gateway-external
         namespace: gateway
     hostnames:
       - "my-service.vanillax.me"
   ```
3. **Commit and push** - ArgoCD syncs, ExternalDNS creates DNS record automatically
4. **Done!** Your service is now accessible at `my-service.vanillax.me`

## Keeping Services Internal (Default)

To keep a service ONLY on your LAN:

1. **Use `gateway-internal`** in the parentRefs
2. **Do NOT add** the `external-dns.alpha.kubernetes.io/target` annotation
3. **Example**:
   ```yaml
   apiVersion: gateway.networking.k8s.io/v1
   kind: HTTPRoute
   metadata:
     name: my-private-service
     namespace: my-namespace
     # NO external-dns annotation!
   spec:
     parentRefs:
       - name: gateway-internal  # Use internal gateway
         namespace: gateway
     hostnames:
       - "private.vanillax.me"
   ```

## Troubleshooting

### ExternalDNS not creating records
```bash
# Check if ExternalDNS is running
kubectl get pods -n external-dns

# Check logs for errors
kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns

# Verify Cloudflare API token secret exists
kubectl get secret -n external-dns cloudflare-api-token

# Check if HTTPRoute has correct annotation
kubectl get httproute <route-name> -n <namespace> -o yaml | grep external-dns
```

### DNS records not resolving
```bash
# Check if record exists in Cloudflare
dig search.vanillax.me @1.1.1.1

# Verify tunnel is running
kubectl get pods -n cloudflared

# Check tunnel logs
kubectl logs -n cloudflared -l app=cloudflared
```

## Security Notes

1. **DNS is the security boundary**: No DNS record = no public access
2. **Internal services never touch Cloudflare**: They have no DNS records in Cloudflare
3. **Audit regularly**: Review which services have the external-dns annotation
4. **Least privilege**: Only expose what needs to be public

## Files in This Directory

- `values.yaml`: Helm values for ExternalDNS
- `cloudflare-external-secret.yaml`: 1Password integration for Cloudflare API token
- `kustomization.yaml`: Kustomize configuration
- `ns.yaml`: Namespace definition
- `README.md`: This file

## Related Documentation

- Cloudflare Tunnel config: `infrastructure/networking/cloudflared/config.yaml`
- Gateway External: `infrastructure/networking/gateway/gw-external.yaml`
- Gateway Internal: `infrastructure/networking/gateway/gw-internal.yaml`
