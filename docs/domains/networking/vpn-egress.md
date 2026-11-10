# VPN egress for pods (Proton WireGuard in the cluster)

This page explains how pod internet traffic leaves the cluster through Proton VPN,
how to turn that on and off, and how to roll it out. It is for anyone who operates
the cluster network or debugs why a site blocks a pod.

Git holds the phase 1 configuration, which covers only the `vpn-egress-test`
namespace. Phases 2 and 3 are planned. Each phase is live only after the manual
steps in [Rollout](#rollout) run.

| What | Where |
|---|---|
| Manifests | [`infrastructure/networking/vpn-egress/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/infrastructure/networking/vpn-egress) |
| Cilium switch | `egressGateway.enabled` in [`infrastructure/networking/cilium/values.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/networking/cilium/values.yaml) |
| Toggle and status page | <https://vpn.vanillax.me> (LAN only) |
| Grafana | Cluster, then VPN egress (`/d/vpn-egress`) |

## Why the VPN runs in the cluster

The Firewalla router sends all cluster traffic through one Proton WireGuard tunnel.
WireGuard encryption pins all 4 Firewalla cores at 98-100%, which caps cluster
downloads at about 670 Mbps on a 2 Gb line. Without the VPN the router is about 61%
idle.

The VPN stays, and this design moves the encryption onto cluster CPUs. Some sites
block VPN IPs (Reddit, YouTube, Okta logins), so the VPN also needs a quick off
switch.

## How it works

```text
pod ──(VXLAN)──> gateway node ──wg-proton (kernel WireGuard)──> Proton server ──> internet
                     │
                     └─ Cilium Egress Gateway SNATs the pod to 10.2.0.2 and sends it out wg-proton

vpn-gateway (DaemonSet, 3 nodes)  ──writes health──>  ConfigMap vpn-gateway-<node>
vpn-egress-controller (1 pod)     ──reads health + on/off──>  creates or deletes CiliumEgressGatewayPolicy vpn-egress
UI vpn.vanillax.me / Home Assistant ──POST /api/enabled──>  ConfigMap vpn-egress-state
```

Three nodes are gateways, and each has its own Proton config: `hp-elite-gen13`,
`mini-pc-dell-ultra-worker`, and `hp-elite-gen12`.

The `vpn-gateway` DaemonSet runs in the host network of those nodes. It creates the
kernel WireGuard link `wg-proton` from the node's Proton config. Every 15 s it probes
through the tunnel. It writes health, exit IP, handshake time, and byte counters to
ConfigMap `vpn-gateway-<node>`.

The `vpn-egress-controller` Deployment owns the `CiliumEgressGatewayPolicy` named
`vpn-egress`. This policy is the object that tells Cilium to send pod traffic out
through a gateway node. Every 10 s the controller does this:

1. It reads the on/off state from ConfigMap `vpn-egress-state`.
2. It picks the healthy gateways. A healthy gateway has a passing probe, a status
   younger than 60 s, and a node that is Ready and not cordoned.
3. It sets the policy from the result:

| State | What the controller does |
|---|---|
| On, with healthy gateways | Applies the policy with only those gateways |
| On, with no healthy gateway | Deletes the policy, so pods use the normal path. This is the fallback. There is no kill switch |
| Off | Deletes the policy |

Cilium assigns each pod to one gateway by a hash of its endpoint UID, so load
spreads across the gateways. The controller serves the web UI, a JSON API, and
Prometheus metrics on one port.

### Why the policy is not in Git

Argo CD self-heal would put a Git-managed policy back after every toggle, so the
toggle could not work. The controller and its RBAC are in Git. The policy and the
two kinds of state ConfigMaps are not.

Argo CD ignores those objects, because it tracks only objects that carry its
tracking label and annotation. No `ignoreDifferences` or `IgnoreExtraneous` rule is
needed.

The `vpn-egress` Namespace is the owner of the policy. If you delete that namespace,
Kubernetes deletes the policy, and pods go back to the normal path.

## Turn it on and off

On the web, open <https://vpn.vanillax.me> and flip the switch. Turning it off asks
for confirmation.

With the API:

```bash
curl -s https://vpn.vanillax.me/api/enabled                     # {"enabled": true, "mode": "on"}
curl -s -X POST https://vpn.vanillax.me/api/enabled \
  -H 'X-VPN-Toggle: 1' -H 'Content-Type: application/json' -d '{"enabled": false}'
```

Home Assistant runs in the cluster, so it uses the Service directly. Add this to
`configuration.yaml`:

```yaml
switch:
  - platform: rest
    name: Cluster VPN
    resource: http://vpn-egress-controller.vpn-egress.svc.cluster.local/api/enabled
    body_on: '{"enabled": true}'
    body_off: '{"enabled": false}'
    is_on_template: "{{ value_json.enabled }}"
    headers:
      Content-Type: application/json
      X-VPN-Toggle: "1"
      X-VPN-Client: home-assistant
```

Add a sensor for the fallback state in Home Assistant's existing `rest:` block:

```yaml
rest:
  - resource: http://vpn-egress-controller.vpn-egress.svc.cluster.local/api/enabled
    scan_interval: 30
    sensor:
      - name: Cluster VPN mode   # on, off or fallback
        value_template: "{{ value_json.mode }}"
```

`mode` has three values:

| `mode` | Meaning |
|---|---|
| `on` | Pods use Proton |
| `off` | The toggle is off |
| `fallback` | The toggle is on, but no gateway is healthy |

The state survives controller restarts, because it is in ConfigMap
`vpn-egress-state`. `DEFAULT_ENABLED` in `config.env` applies only when that
ConfigMap does not exist yet.

### What "off" means before phase 3

While the Firewalla VPN rule for the cluster nodes exists, the normal path for pods
is still the Firewalla's Proton tunnel. Until phase 3, this has two effects:

- VPN off in the UI sends covered pods back through the Firewalla VPN, not the home
  IP. Sites that block VPN IPs stay blocked.
- The fallback also uses the Firewalla VPN, so nothing leaks.

After phase 3 retires the Firewalla VPN rule, off and fallback use the home IP. If
you need the home IP for one site before then, add a Firewalla route rule for that
site.

## Which traffic uses the VPN

### Traffic that stays off the VPN

- In-cluster traffic, Service IPs, and the LAN. The policy excludes `10.0.0.0/8`,
  `100.64.0.0/10`, `169.254.0.0/16`, `172.16.0.0/12` and `192.168.0.0/16`. That
  keeps the NAS (`.133`), the Pi (`.15`), and the LoadBalancer pool direct.
- Host traffic. Talos itself, containerd image pulls, and `hostNetwork` pods are
  not pods to Cilium, so Egress Gateway never touches them.
- Exempt namespaces, listed below.

### Covered and exempt namespaces

Both lists are in [`config.env`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/networking/vpn-egress/config.env).
Phase 1 sets `INCLUDE_NAMESPACES=vpn-egress-test`, so only that namespace is covered.
Phase 2 empties the value, so every namespace is covered except `EXEMPT_NAMESPACES`.

`kube-system` and `vpn-egress` are always exempt, whatever the config says. The UI
lists the live covered and exempt namespaces.

| Exempt namespace | Why |
|---|---|
| `kube-system` | CoreDNS and Cilium must keep working when every tunnel is down. |
| `argocd` | Argo CD must reach GitHub to roll back a broken VPN change. |
| `1passwordconnect`, `external-secrets` | Secrets, including the Proton keys, must sync when the tunnels are down. |
| `vpn-egress` | The gateways and the controller. |
| `cloudflared` | The Cloudflare tunnel stays on the home connection by design. |
| `consumers-energy-sync` | Okta asks for step-up MFA from datacenter VPN IPs. |
| `vllm`, `comfyui` | Large public model downloads from huggingface.co. The VPN adds no privacy there and costs speed. |

Keep this table and `EXEMPT_NAMESPACES` in `config.env` the same.

## What happens when something fails

The design falls back to the normal path. It does not block traffic when the VPN is
down.

| Failure | What happens |
|---|---|
| One tunnel stops passing traffic | 3 failed probes (~45 s) mark it down. The controller drops it within 10 s. Pods move to the other gateways. |
| All tunnels down | The controller deletes the policy. Pods use the normal path. The UI shows a red "VPN down — traffic on home IP" banner. |
| A tunnel recovers | It rejoins after 2 good checks in a row, so a flapping tunnel does not keep re-hashing pods. |
| Gateway node powers off or is cordoned | Status goes stale (60 s) or the node is NotReady/cordoned. The controller drops it. |
| Gateway pod restarts | The kernel tunnel keeps forwarding. The pod reuses the link on start. |
| Controller restarts | It reads the live policy first and keeps those gateways, so a restart does not flap traffic. While it is down the policy stays as it was. |
| `wg-proton` recreated (new ifindex) | The controller writes `node=ifindex` into a policy annotation. The change makes Cilium re-read the link (Cilium re-reads gateway links only on policy or node events: `pkg/egressgateway/manager.go` at `v1.20.4`). |

The `ip rule from 10.2.0.2` and its blackhole route stay on each gateway. They are
not a kill switch. They only stop a packet that Cilium already SNATed to `10.2.0.2`
from leaving on the LAN NIC.

## Known gaps

**DNS still goes to the Firewalla.** A pod lookup goes from the pod to CoreDNS, then
to Talos host DNS, then to the Firewalla (`192.168.10.1`). That path is outside the
Proton tunnel. While the Firewalla VPN rule exists, the Firewalla's own lookups go
through its tunnel, so nothing leaks. Before phase 3, CoreDNS must forward upstream
through the tunnel, either to Proton's in-tunnel resolver `10.2.0.1` or with
DNS-over-HTTPS from the gateways. Otherwise every lookup goes to the ISP once the
Firewalla rule is gone. This is not built. See [Follow-ups](#follow-ups).

**New pods leak for about a second.** Cilium applies the policy shortly after a pod
starts. Traffic in that window leaves with the node IP
([Cilium docs](https://docs.cilium.io/en/v1.20/network/egress-gateway/egress-gateway/#delay-for-enforcement-of-egress-policies-on-new-pods)).
While the Firewalla VPN rule stays on, that traffic still goes through the Firewalla
tunnel.

**Toggling and gateway changes reset connections.** Turning the VPN on or off
changes the source IP of open connections. Adding or removing a gateway re-hashes
pods across gateways ([cilium/cilium#39245](https://github.com/cilium/cilium/issues/39245)).
Apps reconnect.

**Up to ~55 s of drops when the last tunnel dies.** That is 45 s of failed probes
plus one controller loop, before the fallback.

**No IPv6.** Pods are IPv4-only (`enable-ipv6: false`), and the gateway never
configures an IPv6 address.

**MTU mismatch.** Pods send up to 1450-byte packets, and `wg-proton` uses 1420.
Large uploads may fragment the outer packets. Check upload speed in phase 1.

**The UI has no login.** It is on the internal Gateway only (LAN and Tailscale),
like Longhorn and Headlamp. The toggle needs the `X-VPN-Toggle: 1` header. A browser
cannot send that header cross-site without a CORS preflight, and the controller
never answers one. That blocks toggles from other web pages.

## Throughput (expected, not measured)

- Each gateway links at 1 Gb/s. Checked live on 2026-11-03 with node-exporter
  `node_network_speed_bytes`: `hp-elite-gen12` `eno1`, `hp-elite-gen13` `eno1` and
  `mini-pc-dell-ultra-worker` `enp128s31f6` all report 1000 Mb/s, and none has a
  second NIC. If a NIC is 2.5G-capable, the cable or switch port holds it at 1 Gb/s.
- One gateway tops out near 940 Mbps. A single pod uses one gateway, so it also
  peaks near 940 Mbps, above the 670 Mbps cap of the router tunnel.
- Many pods spread across three gateways, so the cluster total can reach the 2 Gb
  line.
- WireGuard crypto runs in kernel softirq on the gateway node. Expect about 1-2
  cores per gateway at full speed.

## Metrics

The controller exposes `/metrics` (ServiceMonitor `vpn-egress-controller`):

| Metric | Meaning |
|---|---|
| `vpn_egress_enabled` | Toggle on (1) or off (0). |
| `vpn_egress_policy_active` | 1 while the policy exists and covered pods use Proton. |
| `vpn_egress_fallback` | 1 when on but no gateway is healthy. |
| `vpn_egress_gateway_up{gateway}` | Probe through that tunnel works. |
| `vpn_egress_gateway_in_policy{gateway}` | The policy uses that gateway. |
| `vpn_egress_gateway_handshake_age_seconds{gateway}` | Seconds since the last WireGuard handshake (renews about every 2 min). |
| `vpn_egress_gateway_receive_bytes_total{gateway}`, `..._transmit_bytes_total` | Tunnel bytes down / up. |
| `vpn_egress_gateway_info{gateway,exit_ip,endpoint}` | Current exit IP and Proton server. |
| `vpn_egress_namespaces{coverage}` | Covered and exempt namespace counts. |

## Rollout

The rollout has three phases. Phase 1 covers one test namespace. Phase 2 covers
every namespace that is not exempt. Phase 3 retires the Firewalla VPN rule.

Steps marked (owner) need the owner's accounts or the router. Hermes can open the
phase 2 PR.

1. **(Owner) Create three Proton WireGuard configs.** Go to
   <https://account.protonvpn.com/downloads>, section WireGuard. Name them after the
   nodes. Pick a different nearby server for each one. Turn NetShield, Moderate NAT
   and NAT-PMP off. Download each `.conf`.
2. **(Owner) Store them in 1Password** (desktop, zsh):

    ```bash
    op item create --vault homelab-prod --category password --title proton-wireguard-egress \
      "hp-elite-gen13[password]=$(base64 -w0 < hp-elite-gen13.conf)" \
      "mini-pc-dell-ultra-worker[password]=$(base64 -w0 < mini-pc-dell-ultra-worker.conf)" \
      "hp-elite-gen12[password]=$(base64 -w0 < hp-elite-gen12.conf)"
    rm hp-elite-gen13.conf mini-pc-dell-ultra-worker.conf hp-elite-gen12.conf
    ```

3. **(Owner) In Firewalla, send the three Proton endpoint IPs to the WAN, not the
   VPN.** Add a route rule for the cluster nodes with each `Endpoint` IP from the
   configs as the target and "Internet" as the route. Give it priority over the
   existing VPN rule. Without it, the cluster tunnels run inside the Firewalla
   tunnel and the router stays the bottleneck.
4. **Merge the PR.** Argo CD enables Egress Gateway in Cilium, rolls the operator
   and deploys `vpn-egress`.
5. **(Owner) Restart the Cilium agents**, one node at a time:

    ```bash
    kubectl -n kube-system rollout restart ds/cilium
    kubectl -n kube-system rollout status ds/cilium --timeout=30m
    kubectl get crd ciliumegressgatewaypolicies.cilium.io
    ```

    Until the restart finishes, the UI shows `policy update failed: 404`. That is
    expected.

6. **Check phase 1.** Open <https://vpn.vanillax.me>. Expected result: 3 gateways
   up with Proton exit IPs, and VPN on. Then run:

    ```bash
    kubectl -n vpn-egress get cm -l app.kubernetes.io/component=gateway-status          # 3 ConfigMaps
    kubectl get ciliumegressgatewaypolicy vpn-egress                                     # exists
    kubectl -n kube-system exec ds/cilium -- cilium-dbg bpf egress list                  # probe pod IP -> 10.2.0.2
    kubectl -n vpn-egress-test exec deploy/egress-probe -- curl -s https://ipinfo.io/ip  # a Proton IP
    kubectl -n vpn-egress-test exec deploy/egress-probe -- speedtest-cli --simple        # > 670 Mbps down
    ```

    Test the toggle. Flip the switch off and run the `ipinfo` line again. It shows
    the Firewalla's Proton IP until phase 3. Flip the switch back on.

    Test the fallback. Remove the Proton peer on all three gateways, wait about a
    minute, and check. Then restart the gateway pods to restore the peers.

    ```bash
    for p in $(kubectl -n vpn-egress get pod -l app=vpn-gateway -o name); do
      kubectl -n vpn-egress exec "$p" -- sh -c 'wg set wg-proton peer "$(wg show wg-proton peers)" remove'; done
    # ~60 s later: red "VPN down" banner, no policy, and egress-probe still gets an IP (the normal path)
    kubectl get ciliumegressgatewaypolicy vpn-egress                                     # NotFound
    kubectl -n vpn-egress-test exec deploy/egress-probe -- curl -s -m 5 https://ipinfo.io/ip
    kubectl -n vpn-egress delete pod -l app=vpn-gateway                                  # restarts reload the configs
    ```

7. **Phase 2 (separate PR).** In `config.env`, set `INCLUDE_NAMESPACES=` (empty).
   After the merge, the UI lists many covered namespaces. Check that an exempt
   namespace still uses the normal path.
8. **Phase 3 (owner).** Wait for a week of phase 2 and for the DNS follow-up. Then
   retire the Firewalla VPN rule for the cluster nodes. Only then do "off" and the
   fallback use the home IP.

## Rollback

- **Fastest.** Flip the switch off at <https://vpn.vanillax.me>. Pods use the normal
  path within 10 s.
- **If the controller is broken.** Run `kubectl delete ciliumegressgatewaypolicy vpn-egress`.
  Then scale the controller to 0 so it does not recreate the policy.
- **Full.** Revert the PR in Git. The policy has no Git owner, so delete it by hand
  as above, or delete the `vpn-egress` namespace, which garbage-collects it. The
  leftover `wg-proton` link and `ip rule` are unused and go away at the next reboot.
- **Phase 3.** Turn the Firewalla VPN rule back on.

## Add or replace a gateway

1. Add the node's Proton config to the 1Password item.
2. In one PR, change the node name in `daemonset.yaml` (affinity), `config.env`
   (`GATEWAY_NODES`), `rbac.yaml` (status ConfigMap names) and `external-secret.yaml`.
3. Keep at least two gateways up during the change.

## Options considered

| Option | Verdict | Why |
|---|---|---|
| **Cilium Egress Gateway + kernel WireGuard on gateway nodes** | **Chosen** | Native to our Cilium 1.20.4, cluster-wide by selector, multiple gateways spread load. Cilium 1.20 redirects to the policy's `interface` (`bpf/bpf_overlay.c`); [cilium/cilium#40406](https://github.com/cilium/cilium/issues/40406) shows the policy-routing fallback we also install. Works on Talos ([siderolabs/talos#12054](https://github.com/siderolabs/talos/issues/12054)). |
| pod-gateway (gateway pod + webhook-injected VXLAN client) | Rejected | Each client pod needs `NET_ADMIN`, which Pod Security baseline forbids ([PSS](https://kubernetes.io/docs/concepts/security/pod-security-standards/)). One gateway pod per namespace, no load spreading. Light maintenance: last image [v1.13.0](https://github.com/angelnu/pod-gateway/releases) in May 2025. |
| gluetun sidecar per app | Rejected for cluster-wide | Good kill switch and kernel WireGuard ([gluetun wiki](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/wireguard.md)), but one tunnel and one Proton device per pod, plus `NET_ADMIN` in every app. Still fine for a single app that needs its own exit. |
| Talos `WireguardConfig` on nodes + Cilium routing | Rejected | Talos can create the link at boot ([Talos 1.14 WireguardConfig](https://docs.siderolabs.com/talos/v1.14/reference/configuration/network/wireguardconfig)), but the private key would live in the Omni machine config, not in 1Password. Changes need an Omni template sync. No health signal to Cilium. |
| Toggle by a Git-managed policy + Argo `ignoreDifferences` | Rejected | Argo would still recreate a deleted policy, so "off" and the fallback would need a fake selector instead of no policy. A controller-owned object is simpler. |

## Follow-ups

- **Phase 3 DNS.** Forward CoreDNS upstream through the tunnel before you retire
  the Firewalla VPN rule. Use Proton's `10.2.0.1` through a gateway, or DoH from the
  gateways.
- **Per-site home exit.** If toggling the whole VPN gets annoying, add
  per-destination exclusions (`excludedCIDRs`) for sites that block VPN IPs.
