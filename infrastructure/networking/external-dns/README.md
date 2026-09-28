# ExternalDNS

This component deploys two isolated ExternalDNS instances:

- `external-dns` manages labeled public routes in Cloudflare.
- `external-dns-technitium` manages private `vanillax.me` overrides in
  Technitium at `192.168.10.15:53`.

Both instances use the same DNS suffix safely because their Gateway filters
do not overlap:

- Cloudflare watches `gateway-external`.
- Technitium watches `gateway-internal-technitium`.

## Technitium Instance

The RFC2136 instance uses:

- Zone: `vanillax.me` Conditional Forwarder zone
- Gateway address: `192.168.10.52`
- TSIG key: `externaldns-vanillax`
- TSIG algorithm: `hmac-sha256`
- 1Password item: `external-dns-technitium-vanillax`
- 1Password field: `tsig-secret`
- TXT owner ID: `talos-prod-technitium`
- TXT prefix: `external-dns-`

Technitium-generated TSIG values are already Base64. The ExternalSecret trims
and passes the value through unchanged. Do not apply `b64enc` again and never
store or print the secret.

The `allow-technitium-dns` CiliumNetworkPolicy permits only this ExternalDNS
pod to reach `192.168.10.15` on TCP/UDP port 53.

`policy=upsert-only` remains intentional until the complete short-name
migration and TXT ownership state have been observed. Do not enable `sync`
without a separate review.

The Conditional Forwarder zone keeps local private records while forwarding
missing `vanillax.me` records to Cloudflare. A Primary zone must not be used
because it would return NXDOMAIN instead of forwarding missing public names.

See the complete setup and cutover runbook:

[`docs/domains/networking/technitium-vanillax-me-migration.md`](../../../docs/domains/networking/technitium-vanillax-me-migration.md)

## Route Contract

Private HTTPRoutes attach to the labeled Technitium Gateway:

```yaml
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: gateway-internal-technitium
      namespace: gateway
      sectionName: https
  hostnames:
    - app.vanillax.me
```

Public routes continue attaching to `gateway-external` and retain their
Cloudflare ExternalDNS label.

## Validation

```bash
kubectl -n external-dns get pods
kubectl -n external-dns logs deploy/external-dns-technitium -f
dig @192.168.10.15 argocd.vanillax.me +short
dig @192.168.10.1 argocd.vanillax.me +short
dig @192.168.10.15 homeassistant.vanillax.me +short
dig @192.168.10.1 homeassistant.vanillax.me +short
```
