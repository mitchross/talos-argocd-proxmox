# Site won't load: split DNS, gateways, Cloudflare, Tailscale

Covers a `*.vanillax.me` site that loads for some clients but not others (LAN, Tailscale, phone data), a browser network error, or Tailscale not routing traffic home.

## Procedure (in order)

1. **Server side.** `kubectl -n <ns> get pods,httproute`, the Argo app status, then `curl -sk -o /dev/null -w '%{http_code} %{time_total}\n' https://<host>/` from the pod. A fast 200 means the app is fine; stop blaming it.
2. **Real browser.** Load the page with browser_exec and read `document.body.innerText`. The Chrome error code (`ERR_QUIC_PROTOCOL_ERROR`, `ERR_ECH_*`, `ERR_NAME_NOT_RESOLVED`) picks the branch.
3. **Route type.** Check the HTTPRoute `parentRefs`: internal only, public only, or both (dual-homed, same hostname on both gateways).
4. **DNS by record type.** Query A, AAAA and HTTPS (type 65) for the broken host and for a working host of the same kind:
   - Cluster view: the resolver in `/etc/resolv.conf` (10.96.0.10). The pod has no `dig`, so send a raw UDP query from Python.
   - Technitium view (what LAN and Tailscale clients get): `ssh pi 'dig +short @192.168.10.15 <host> A; dig +short @192.168.10.15 <host> AAAA; dig +short @192.168.10.15 <host> HTTPS'`. The pod can't reach 192.168.10.15:53 directly.
   - `getent hosts` prints IPv6 first; `getent ahostsv4` shows the A record curl used.
5. **Public path.** `curl --resolve <host>:443:<cloudflare-ip> https://<host>/`. A 200 plus cloudflared pods Running with no restarts means Cloudflare is healthy.

## Known causes

| Symptom | Cause | Fix |
|---|---|---|
| Dual-homed host fails on LAN/Tailscale with `ERR_QUIC_PROTOCOL_ERROR`; internal-only and public-only hosts work | The Technitium Forwarder zone answers A locally (192.168.10.52) but forwards AAAA and HTTPS to Cloudflare. The HTTPS record carries `alpn=h3`, Cloudflare ipv4hints and an `ech=` key, so the browser tries HTTP/3 and ECH against the LAN gateway | Add a Technitium Primary zone for that exact hostname holding only `A 192.168.10.52`, so AAAA and HTTPS return empty. Hand-managed state on the Pi (external-dns won't own it): explain and get a yes first |
| Tailscale client: public sites still use the local (guest/work) network; blocked sites stay blocked | No exit node selected, so only the tailnet and `192.168.10.0/24` go home | Exit-node recipe below |

If the user asks for a cloudflared restart anyway: `kubectl -n cloudflared rollout restart deploy/cloudflared` (rolling, safe), then report before/after.

## Tailscale full tunnel through the TrueNAS app

Goal: the phone sends all traffic home and still resolves `vanillax.me` through Technitium.

1. **TrueNAS app.** Apps → tailscale → Edit → Advertise Exit Node. With **Auth Once** ticked, Advertise Exit Node, Accept Routes and Extra Arguments apply only at first login; ticking them later does nothing (admin console: "This device does not advertise itself as an exit node"). To apply: untick Auth Once, paste a fresh auth key (admin console → Settings → Keys), Update, wait for the Exit Node badge, re-tick Auth Once. Hostname and Advertise Routes re-apply on every start.
2. **IP forwarding.** Apps (Docker) already enables it. Check in System → Shell with `sysctl net.ipv4.ip_forward`; add a tunable only if it shows 0. TrueNAS runs a nightly build, so trust the shell check over the UI/docs.
3. **Admin console.** Machines → truenas → Edit route settings → Use as exit node; keep the subnet route ticked.
4. **DNS.** With an exit node selected, the exit node answers all DNS and split DNS is skipped. Turn on **Use with exit node** for the `vanillax.me` → 192.168.10.15 nameserver. **Override DNS servers** stops clients using the local network's DNS.
5. **Phone.** Exit node → truenas, Allow LAN access off.

If the network blocks UDP, Tailscale falls back to DERP relays: slower, still works.
