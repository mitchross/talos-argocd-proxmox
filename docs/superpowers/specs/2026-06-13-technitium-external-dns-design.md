# Technitium ExternalDNS Design

## Goal

Deploy a second ExternalDNS instance for the Talos cluster that manages only
`internal.vanillax.me` through Technitium DNS at `192.168.10.15:53` using
RFC2136 and TSIG.

## Architecture

The cluster keeps the existing `cilium` GatewayClass and uses three Gateway
resources:

- `gateway-external` for public Cloudflare-routed services.
- `gateway-internal` for the established `*.vanillax.me` LAN routes.
- `gateway-internal-technitium` at `192.168.10.52` for the test
  `*.internal.vanillax.me` routes.

The existing Cloudflare ExternalDNS Helm release remains unchanged. A second
release, `external-dns-technitium`, runs in the same `external-dns` namespace
and uses the existing chart version and security/resource conventions.

## DNS And Secret Flow

ExternalDNS watches labeled Gateway API HTTPRoutes attached to
`gateway-internal-technitium`. It writes only names below
`internal.vanillax.me` to Technitium using RFC2136.

The TSIG secret comes from the `external-dns-technitium` 1Password item,
field `tsig-secret`, through the existing `ClusterSecretStore/1password`.
The secret is never stored in Git.

## TLS

The new Gateway has HTTP and HTTPS listeners for
`*.internal.vanillax.me`. The existing `cloudflare-cluster-issuer` issues the
publicly trusted wildcard certificate with DNS-01. Cloudflare is used only
for temporary ACME TXT validation records; internal application records stay
in Technitium.

## Safety

- `policy=upsert-only` prevents record deletion during the test rollout.
- `registry=txt`, owner ID `talos-prod-internal`, and prefix
  `external-dns-` track ownership.
- `domain-filter=internal.vanillax.me` and the RFC2136 zone constrain writes.
- HTTPRoute and Gateway label filters isolate the Technitium and Cloudflare
  ExternalDNS instances.
- Ingress is not enabled because this repository uses Gateway API
  exclusively and contains no Ingress resources.

## Validation

Render the Kustomize applications with Helm enabled, inspect the generated
Deployment arguments and environment reference, run the Argo CD application
validator, and use client-side Kubernetes validation on the rendered output.
After Argo CD sync, verify the pod, logs, Gateway status, certificate, and DNS
answers through both Technitium and Firewalla.
