---
name: homelab-network-access
description: Use when a homelab site won't load on LAN or Tailscale.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [DNS, Technitium, Tailscale, Cloudflare, Gateway-API, Split-DNS]
    category: devops
---

# Homelab network access: why a site won't load

## When to Use

A `*.vanillax.me` site loads for some clients but not others (LAN, Tailscale, phone data), shows a browser network error, or Tailscale doesn't route traffic home. Covers split DNS, the two gateways, Cloudflare and Tailscale routing. For pod, Argo or Longhorn health, use `homelab-ops`.

Layout: `gateway-external` (192.168.10.49) serves public names through Cloudflare (cloudflared tunnel, external-dns to Cloudflare). `gateway-internal-technitium` (192.168.10.52) serves LAN names; external-dns writes A records over RFC2136 into Technitium on the Pi (192.168.10.15). Technitium's `vanillax.me` zone is a **Forwarder** zone. Remote devices reach the LAN through the TrueNAS Tailscale app (subnet route `192.168.10.0/24`, split DNS `vanillax.me` -> 192.168.10.15).

## Procedure (in order)

1. **Server side.** `kubectl -n <ns> get pods,httproute`, the Argo app status, then `curl -sk -o /dev/null -w '%{http_code} %{time_total}\n' https://<host>/` from the pod. A fast 200 here means the app is fine; stop blaming it.
2. **Real browser.** Load the page with browser_exec and read `document.body.innerText`. The Chrome error code (`ERR_QUIC_PROTOCOL_ERROR`, `ERR_ECH_*`, `ERR_NAME_NOT_RESOLVED`) picks the branch. curl hides HTTP/3 and ECH problems because it never reads the DNS HTTPS record.
3. **Route type.** Check the HTTPRoute `parentRefs`: internal only, public only, or **both** (dual-homed, same hostname on both gateways). Dual-homed hosts are where split DNS leaks.
4. **DNS by record type.** Query A, AAAA and HTTPS (type 65) for the broken host and for a working host of the same kind:
   - The cluster view comes from the resolver in `/etc/resolv.conf` (10.96.0.10). There is no `dig` in the pod, so send a raw UDP query from Python.
   - For the Technitium view (what LAN and Tailscale clients get), run `ssh pi 'dig +short @192.168.10.15 <host> A; dig +short @192.168.10.15 <host> AAAA; dig +short @192.168.10.15 <host> HTTPS'`. The pod cannot reach 192.168.10.15:53 directly, so go through `ssh pi`.
   - `getent hosts` prints IPv6 first; use `getent ahostsv4` to see the A record curl actually used.
5. **Public path.** `curl --resolve <host>:443:<cloudflare-ip> https://<host>/`. A 200 here, plus cloudflared pods Running with no restarts, means Cloudflare is healthy.

## Known causes

| Symptom | Cause | Fix |
|---|---|---|
| Dual-homed host fails on LAN or Tailscale with `ERR_QUIC_PROTOCOL_ERROR`; internal-only and public-only hosts work | The Technitium Forwarder zone answers A locally (192.168.10.52) but forwards AAAA and HTTPS to Cloudflare. The HTTPS record carries `alpn=h3`, Cloudflare ipv4hints and an `ech=` key, so the browser tries HTTP/3 and ECH against the LAN gateway | In Technitium, add a Primary zone for that exact hostname holding only `A 192.168.10.52`, so AAAA and HTTPS return empty. This is hand-managed state on the Pi (external-dns won't own it), so explain it and get a yes first |
| Tailscale client: public sites still use the local (guest/work) network, and blocked sites stay blocked | No exit node is selected, so only the tailnet and `192.168.10.0/24` go home | Use an exit node; see `references/tailscale-truenas-exit-node.md` |

## Rules

- Restarting cloudflared does not change LAN or Tailscale DNS answers. Say so once with evidence (pod age, the `--resolve` 200). If the user still asks for the restart, run `kubectl -n cloudflared rollout restart deploy/cloudflared` right away (it is rolling and safe), then report the before/after result. Don't argue a second time.
- Compare against a working host of the same route type before naming a cause. The difference between the two is usually the cause.
- Technitium, Tailscale admin and TrueNAS are not Git-owned. Changes there are direct; describe the effect and how to undo it.
