# ExternalDNS

This component deploys two ExternalDNS instances:

- `external-dns` manages selected public `vanillax.me` records in Cloudflare.
- `external-dns-technitium` manages only `internal.vanillax.me` in
  Technitium DNS at `192.168.10.15:53`.

## Technitium Instance

The internal instance uses RFC2136 with:

- TSIG key name: `externaldns-internal`
- TSIG algorithm: `hmac-sha256`
- 1Password item: `external-dns-technitium`
- 1Password field: `tsig-secret`
- TXT owner ID: `talos-prod-internal`
- TXT prefix: `external-dns-`

The TSIG value is populated by External Secrets through the existing
`ClusterSecretStore/1password`; it must never be stored in Git.

`policy=upsert-only` is intentional for the initial rollout. It allows record
creation and updates without deleting existing records. Do not switch to
`sync` until Technitium records and TXT ownership have been verified.

Only Gateway API HTTPRoutes with the internal scope label and the dedicated
Gateway are processed:

```yaml
metadata:
  labels:
    external-dns-scope: internal
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: gateway-internal-technitium
      namespace: gateway
      sectionName: https
  hostnames:
    - app.internal.vanillax.me
```

The Gateway address is `192.168.10.52`. Firewalla remains the client DNS path
and forwards `internal.vanillax.me` to Technitium; this repository does not
change DHCP or client DNS settings.

## Validation

```bash
kubectl -n external-dns get pods
kubectl -n external-dns logs deploy/external-dns-technitium -f
dig @192.168.10.15 technitium.internal.vanillax.me +short
dig @192.168.10.1 technitium.internal.vanillax.me +short
dig @192.168.10.15 <test-host>.internal.vanillax.me +short
dig @192.168.10.1 <test-host>.internal.vanillax.me +short
```
