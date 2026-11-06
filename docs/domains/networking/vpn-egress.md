# VPN egress for pods (Proton WireGuard in the cluster)

**Purpose:** explain how pod internet traffic leaves through Proton VPN, how to turn it on and off, and how to roll it out.
**Status:** plan plus phase 1 manifests. Nothing is live until the rollout steps below run.
**Owner manifests:** [`infrastructure/networking/vpn-egress/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/infrastructure/networking/vpn-egress),
`egressGateway.enabled` in [`infrastructure/networking/cilium/values.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/networking/cilium/values.yaml).
**Toggle and status page:** <https://vpn.vanillax.me> (LAN only). **Grafana:** Cluster → VPN egress (`/d/vpn-egress`).

## Why

Today the Firewalla sends all cluster traffic through one Proton WireGuard tunnel.
WireGuard encryption pins all 4 Firewalla cores at 98-100%, which caps cluster downloads at about 670 Mbps on a 2 Gb line.
Without the VPN the router is about 61% idle. So the VPN stays, but the encryption moves onto cluster CPUs.
Some sites block VPN IPs (Reddit, YouTube, Okta logins), so the VPN also needs a quick off switch.

## Design

```text
pod ──(VXLAN)──> gateway node ──wg-proton (kernel WireGuard)──> Proton server ──> internet
                     │
                     └─ Cilium Egress Gateway SNATs the pod to 10.2.0.2 and sends it out wg-proton

vpn-gateway (StatefulSet, 3 pods) ──writes health──>  ConfigMap vpn-gateway-<ordinal>
vpn-egress-controller (1 pod)     ──reads health + on/off──>  creates or deletes CiliumEgressGatewayPolicy vpn-egress
UI vpn.vanillax.me / Home Assistant ──POST /api/enabled──>  ConfigMap vpn-egress-state
```

- Three floating VPNs, `vpn-gateway-0`, `vpn-gateway-1` and `vpn-gateway-2`.
  Each uses its own Proton config from 1Password item `talos-cluster-global-vpn-config`:
  `config-1`, `config-2` and `config-3`, in that order. The Secret keeps those field names.
- A StatefulSet runs them on any eligible Linux worker, one VPN per node.
  Control-plane nodes are excluded. Existing taints still apply, so the Wi-Fi worker is not eligible today.
  The GPU worker is eligible: these pods request no GPU and need no special hardware.
  Required pod anti-affinity prevents shared host links and tunnel addresses.
  A disruption budget allows one voluntary eviction at a time during drains.
- Kubernetes moves the VPNs when workers are drained or removed; no node list needs editing.
  Each pod creates `wg-proton` on its current node. On exit it marks itself down and removes
  its link, source rule and route table. On start it replaces any leftover link.
  Every 15 s it reports probes, exit IP, handshake and bytes in a ConfigMap with its pod name,
  including its current node and pod UID. Status from an old pod cannot admit a replacement.
- The `vpn-egress-controller` Deployment owns the `CiliumEgressGatewayPolicy` named `vpn-egress`. Every 10 s it:
    - reads the on/off state from ConfigMap `vpn-egress-state`;
    - picks the healthy gateways: probe OK, status younger than 60 s, pod Ready, node Ready and not cordoned;
    - **on, with healthy gateways:** applies the policy with only those gateways;
    - **on, with no healthy gateway:** deletes the policy, so pods use the normal path (fallback, no kill switch);
    - **off:** deletes the policy.
- Cilium assigns each pod to one gateway by a hash of its endpoint UID, so load spreads across the gateways.
- The controller serves the web UI, a JSON API and Prometheus metrics on one port.

### Why the policy is not in Git

Argo CD would put a Git-managed policy back after every toggle (self-heal), so the toggle could not work.
The controller and its RBAC are in Git; the policy and the two kinds of state ConfigMaps are not.
Argo CD ignores them, because it tracks only objects that carry its tracking label and annotation.
So no `ignoreDifferences` or `IgnoreExtraneous` rule is needed.
The policy has the `vpn-egress` Namespace as its owner. Deleting that namespace deletes the policy, and pods go back to the normal path.

### Failure behaviour (fallback, not kill switch)

| Failure | What happens |
|---|---|
| One tunnel stops passing traffic | 3 failed probes (~45 s) mark it down. The controller drops it within 10 s. Pods move to the other gateways. |
| All tunnels down | The controller deletes the policy. Pods use the normal path. The UI shows a red "VPN down — traffic on home IP" banner. |
| A tunnel recovers | It rejoins after 2 good checks in a row, so a flapping tunnel doesn't keep re-hashing pods. |
| Gateway node powers off or is cordoned | Status goes stale (60 s) or the node is NotReady/cordoned. The controller drops it. |
| Gateway pod restarts or moves | Old host state is removed; the new pod rebuilds its tunnel. It rejoins after fresh health checks. Existing connections may reset. |
| Controller restarts | It reads the live policy first and keeps those gateways, so a restart doesn't flap traffic. While it is down the policy stays as it was. |
| `wg-proton` recreated (new ifindex) | The controller writes `node=ifindex` into a policy annotation. The change makes Cilium re-read the link (Cilium re-reads gateway links only on policy or node events: `pkg/egressgateway/manager.go` at `v1.20.4`). |

The `ip rule from 10.2.0.2` and its blackhole route stay while each gateway runs, then are removed on exit.
They are not a kill switch: they only stop a packet that Cilium already SNATed to `10.2.0.2` from leaving on the LAN NIC.

### "Home IP" before phase 3

While the Firewalla VPN rule for the cluster nodes exists, the normal path for pods is still the Firewalla's Proton tunnel.
So until phase 3:

- **VPN off** in the UI sends covered pods back through the Firewalla VPN, not the home IP. Sites that block VPN IPs stay blocked.
- **Fallback** also uses the Firewalla VPN, so nothing leaks.

After phase 3 (Firewalla VPN rule retired), off and fallback really use the home IP.
If you need the home IP for one site before then, add a Firewalla route rule for that site instead.

### What stays off the VPN

- In-cluster traffic, Service IPs and the LAN: the policy excludes `10.0.0.0/8`, `100.64.0.0/10`, `169.254.0.0/16`, `172.16.0.0/12` and `192.168.0.0/16`.
  That keeps the NAS (`.133`), the Pi (`.15`) and the LB pool direct.
- Host traffic: Talos itself, containerd image pulls and `hostNetwork` pods are not pods to Cilium, so Egress Gateway never touches them.
- Exempt namespaces (phase 2), listed below.

### Covered and exempt namespaces

Both lists live in [`config.env`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/networking/vpn-egress/config.env).
Phase 1 sets `INCLUDE_NAMESPACES=vpn-egress-test`, so only that namespace is covered.
Phase 2 empties it, so every namespace is covered except `EXEMPT_NAMESPACES`.
`kube-system` and `vpn-egress` are always exempt, whatever the config says.
The UI lists the live covered and exempt namespaces.

| Exempt namespace | Why |
|---|---|
| `kube-system` | CoreDNS and Cilium must keep working when every tunnel is down. |
| `vpn-egress` | The gateways and the controller. |
| `consumers-energy-sync` | Okta asks for step-up MFA from datacenter VPN IPs. |

Everything else uses the VPN, including Argo CD, External Secrets, 1Password Connect, cloudflared and the model downloaders.
They still work when every tunnel dies, because the controller then deletes the policy (fallback).
If the controller itself is down while the policy points at a dead tunnel, those namespaces lose internet too. Fix: `kubectl delete ciliumegressgatewaypolicy vpn-egress`.

### Known gaps

- **DNS still goes to the Firewalla.** Pod lookups go pod → CoreDNS → Talos host DNS → Firewalla (`192.168.10.1`), outside the Proton tunnel.
  While the Firewalla VPN rule exists, the Firewalla's own lookups go through its tunnel, so nothing leaks.
  **Before phase 3**, CoreDNS must forward upstream through the tunnel (Proton's in-tunnel resolver `10.2.0.1`, or DNS-over-HTTPS from the gateways).
  Otherwise every lookup goes to the ISP once the Firewalla rule is gone. Not built yet; see follow-ups.
- **New pods leak for about a second.** Cilium applies the policy shortly after a pod starts.
  Traffic in that window leaves with the node IP ([Cilium docs](https://docs.cilium.io/en/v1.20/network/egress-gateway/egress-gateway/#delay-for-enforcement-of-egress-policies-on-new-pods)).
  While the Firewalla VPN rule stays on, that traffic still goes through the Firewalla tunnel.
- **Toggling and gateway changes reset connections.** Turning the VPN on or off changes the source IP of open connections.
  Adding or removing a gateway re-hashes pods across gateways ([cilium/cilium#39245](https://github.com/cilium/cilium/issues/39245)). Apps reconnect.
- **Up to ~55 s of drops when the last tunnel dies:** 45 s of failed probes plus one controller loop, before the fallback.
- **A VPN move can drop traffic for about a minute** while the controller removes the old route and the replacement warms up. Other VPNs keep serving.
  Full recovery after an abrupt node loss can take longer: Kubernetes waits for node eviction.
  A StatefulSet may wait until a lost node is removed or fenced before replacing its pod.
  Never force-delete a gateway pod on a node that might still run it: the same Proton key would run twice.
- **A forced kill cannot run cleanup.** A reboot clears host state; a replacement on that host replaces the link.
  Normal exits and drains clean up immediately.
- **IPv6:** pods are IPv4-only (`enable-ipv6: false`), and the gateway never configures an IPv6 address.
- **MTU:** pods send up to 1450-byte packets; `wg-proton` uses 1420. Large uploads may fragment the outer packets. Check upload speed in phase 1.
- **The UI has no login.** It is on the internal Gateway only (LAN and Tailscale), like Longhorn and Headlamp.
  The toggle needs the `X-VPN-Toggle: 1` header, which a browser can't send cross-site without a CORS preflight the controller never answers.
  That blocks drive-by toggles from other web pages.

## Throughput (expected, not measured)

- Speed depends on the workers Kubernetes chooses and the Proton servers. Placement is not tied to a particular NIC or CPU.
- A single pod uses one gateway; many pods can use all three. Measure phase 1 rather than assuming line speed.
- Many pods spread across three gateways, so the cluster total can reach the 2 Gb line.
- WireGuard crypto runs in kernel softirq on the gateway node. Expect about 1-2 cores per gateway at full speed.

## Turn it on and off

- **Web:** open <https://vpn.vanillax.me> and flip the switch. Turning it off asks for confirmation.
- **API:**

    ```bash
    curl -s https://vpn.vanillax.me/api/enabled                     # {"enabled": true, "mode": "on"}
    curl -s -X POST https://vpn.vanillax.me/api/enabled \
      -H 'X-VPN-Toggle: 1' -H 'Content-Type: application/json' -d '{"enabled": false}'
    ```

- **Home Assistant** (in-cluster, so it uses the Service directly). Add to `configuration.yaml`:

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

    A sensor for the fallback state, using HA's existing `rest:` block:

    ```yaml
    rest:
      - resource: http://vpn-egress-controller.vpn-egress.svc.cluster.local/api/enabled
        scan_interval: 30
        sensor:
          - name: Cluster VPN mode   # on, off or fallback
            value_template: "{{ value_json.mode }}"
    ```

`mode` is `on` (pods use Proton), `off` (toggle off) or `fallback` (toggle on, no healthy gateway).
The state survives controller restarts. It lives in ConfigMap `vpn-egress-state`.
`DEFAULT_ENABLED` in `config.env` applies only when that ConfigMap doesn't exist yet.

## Metrics

The controller exposes `/metrics` (ServiceMonitor `vpn-egress-controller`):

| Metric | Meaning |
|---|---|
| `vpn_egress_enabled` | Toggle on (1) or off (0). |
| `vpn_egress_policy_active` | 1 while the policy exists and covered pods use Proton. |
| `vpn_egress_fallback` | 1 when on but no gateway is healthy. |
| `vpn_egress_gateway_up{gateway,node}` | Probe through that tunnel works. |
| `vpn_egress_gateway_in_policy{gateway,node}` | The policy uses that gateway. |
| `vpn_egress_gateway_handshake_age_seconds{gateway,node}` | Seconds since the last WireGuard handshake (renews about every 2 min). |
| `vpn_egress_gateway_receive_bytes_total{gateway,node}`, `..._transmit_bytes_total` | Tunnel bytes down / up. |
| `vpn_egress_gateway_info{gateway,node,exit_ip,endpoint}` | Current exit IP and Proton server. |
| `vpn_egress_namespaces{coverage}` | Covered and exempt namespace counts. |

## Options considered

| Option | Verdict | Why |
|---|---|---|
| **Cilium Egress Gateway + kernel WireGuard on gateway nodes** | **Chosen** | Native to our Cilium 1.20.4, cluster-wide by selector, multiple gateways spread load. Cilium 1.20 redirects to the policy's `interface` (`bpf/bpf_overlay.c`); [cilium/cilium#40406](https://github.com/cilium/cilium/issues/40406) shows the policy-routing fallback we also install. Works on Talos ([siderolabs/talos#12054](https://github.com/siderolabs/talos/issues/12054)). |
| pod-gateway (gateway pod + webhook-injected VXLAN client) | Rejected | Each client pod needs `NET_ADMIN`, which Pod Security baseline forbids ([PSS](https://kubernetes.io/docs/concepts/security/pod-security-standards/)). One gateway pod per namespace, no load spreading. Light maintenance: last image [v1.13.0](https://github.com/angelnu/pod-gateway/releases) in May 2025. |
| gluetun sidecar per app | Rejected for cluster-wide | Good kill switch and kernel WireGuard ([gluetun wiki](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/wireguard.md)), but one tunnel and one Proton device per pod, plus `NET_ADMIN` in every app. Still fine for a single app that needs its own exit. |
| Talos `WireguardConfig` on nodes + Cilium routing | Rejected | Talos can create the link at boot ([Talos 1.14 WireguardConfig](https://docs.siderolabs.com/talos/v1.14/reference/configuration/network/wireguardconfig)), but the private key would live in the Omni machine config, not in 1Password. Changes need an Omni template sync. No health signal to Cilium. |
| Toggle by a Git-managed policy + Argo `ignoreDifferences` | Rejected | Argo would still recreate a deleted policy, so "off" and the fallback would need a fake selector instead of no policy. A controller-owned object is simpler. |

## Rollout

Owner steps are marked **(Mitch)**. Hermes can open the phase 2 PR.

1. **(Mitch) Create three Proton WireGuard configs**, each on a different low-load server in Chicago.
   Go to <https://account.protonvpn.com/downloads>, section WireGuard.
   Name them `talos-cluster-global-vpn-config-1`, `-2` and `-3`. Turn NetShield, Moderate NAT and NAT-PMP off. Download each `.conf`.
2. **(Mitch) Store them in 1Password** (desktop, zsh, in the download folder):

    ```bash
    op item create --vault homelab-prod --category password --title talos-cluster-global-vpn-config \
      "config-1[password]=$(base64 -w0 < talos-cluster-global-vpn-config-1.conf)" \
      "config-2[password]=$(base64 -w0 < talos-cluster-global-vpn-config-2.conf)" \
      "config-3[password]=$(base64 -w0 < talos-cluster-global-vpn-config-3.conf)"
    rm talos-cluster-global-vpn-config-{1,2,3}.conf
    ```

3. **(Mitch) Firewalla: send the three Proton endpoint IPs to the WAN, not the VPN.**
   Add a route rule for the cluster nodes with each config's `Endpoint` IP as the target and "Internet" as the route.
   Give it priority over the existing VPN rule. Without it, the new tunnels run inside the Firewalla tunnel and the router stays the bottleneck.
4. **Merge the PR.** Argo enables Egress Gateway in Cilium, rolls the operator and deploys `vpn-egress`.
5. **(Mitch) Restart the Cilium agents**, one node at a time:

    ```bash
    kubectl -n kube-system rollout restart ds/cilium
    kubectl -n kube-system rollout status ds/cilium --timeout=30m
    kubectl get crd ciliumegressgatewaypolicies.cilium.io
    ```

    Until then the UI shows `policy update failed: 404`. That is expected.

6. **Check phase 1.** Open <https://vpn.vanillax.me>: 3 gateways up with Proton exit IPs, VPN on. Then:

    ```bash
    kubectl -n vpn-egress get cm -l app.kubernetes.io/component=gateway-status          # 3 ConfigMaps
    kubectl get ciliumegressgatewaypolicy vpn-egress                                     # exists
    kubectl -n kube-system exec ds/cilium -- cilium-dbg bpf egress list                  # probe pod IP -> 10.2.0.2
    kubectl -n vpn-egress-test exec deploy/egress-probe -- curl -s https://ipinfo.io/ip  # a Proton IP
    kubectl -n vpn-egress-test exec deploy/egress-probe -- speedtest-cli --simple        # > 670 Mbps down
    ```

    Toggle test: flip the switch off, run the `ipinfo` line again (Firewalla's Proton IP until phase 3), flip it back on.

    Fallback test: remove the Proton peer on all three gateways, wait about a minute, check, then restart the gateway pods to restore it.

    ```bash
    for p in $(kubectl -n vpn-egress get pod -l app=vpn-gateway -o name); do
      kubectl -n vpn-egress exec "$p" -- sh -c 'wg set wg-proton peer "$(wg show wg-proton peers)" remove'; done
    # ~60 s later: red "VPN down" banner, no policy, and egress-probe still gets an IP (the normal path)
    kubectl get ciliumegressgatewaypolicy vpn-egress                                     # NotFound
    kubectl -n vpn-egress-test exec deploy/egress-probe -- curl -s -m 5 https://ipinfo.io/ip
    kubectl -n vpn-egress delete pod -l app=vpn-gateway                                  # restarts reload the configs
    ```

7. **Phase 2 (separate PR).** In `config.env`, set `INCLUDE_NAMESPACES=` (empty).
   After merge, the UI lists many covered namespaces. Check that an exempt namespace still uses the normal path.
8. **Phase 3 (Mitch, after a week of phase 2, and after the DNS follow-up):** retire the Firewalla VPN rule for the cluster nodes.
   Only then do "off" and the fallback really use the home IP.

## Rollback

- Fastest: flip the switch off at <https://vpn.vanillax.me>. Pods use the normal path within 10 s.
- If the controller is broken: `kubectl delete ciliumegressgatewaypolicy vpn-egress`, then scale the controller to 0 so it doesn't recreate it.
- Full: revert the PR in Git. The policy has no Git owner, so delete it by hand as above (or delete the `vpn-egress` namespace, which garbage-collects it).
  Normal pod exits remove `wg-proton`, its source rule and route table. A forced kill may leave unused host state until restart or reboot.
- Phase 3: turn the Firewalla VPN rule back on.

## Add a gateway

Add the next unique Proton config to the same 1Password item (`config-4`, base64-encoded), then in one PR:

- Bump `replicas` in `statefulset.yaml`.
- Add the matching `config-4` entry in `external-secret.yaml`.
- Allow status ConfigMap `vpn-gateway-3` in `rbac.yaml`.

The controller discovers the new VPN automatically. It needs another eligible worker;
if there are fewer workers than VPNs, the extra pod stays Pending rather than sharing a host.
Keep at least two VPNs up during a change.

## Follow-ups

- **Phase 3 DNS:** forward CoreDNS upstream through the tunnel (Proton's `10.2.0.1` via a gateway, or DoH from the gateways) before retiring the Firewalla VPN rule.
- **Per-site home exit:** if toggling the whole VPN gets annoying, add per-destination exclusions (`excludedCIDRs`) for sites that block VPN IPs.
