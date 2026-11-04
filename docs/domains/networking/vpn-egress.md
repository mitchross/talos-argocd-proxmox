# VPN egress for pods (Proton WireGuard in the cluster)

**Purpose:** explain how pod internet traffic leaves through Proton VPN, and how to roll it out.
**Status:** plan plus phase 1 manifests. Nothing is live until the rollout steps below run.
**Owner manifests:** [`infrastructure/networking/vpn-egress/`](https://github.com/mitchross/talos-argocd-proxmox/tree/main/infrastructure/networking/vpn-egress),
`egressGateway.enabled` in [`infrastructure/networking/cilium/values.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/networking/cilium/values.yaml).

## Why

Today the Firewalla sends all cluster traffic through one Proton WireGuard tunnel.
WireGuard encryption pins all 4 Firewalla cores at 98-100%, which caps cluster downloads at about 670 Mbps on a 2 Gb line.
Without the VPN the router is about 61% idle. So the VPN stays, but the encryption moves onto cluster CPUs.

## Design

```text
pod ──(VXLAN)──> gateway node ──wg-proton (kernel WireGuard)──> Proton server ──> internet
                     │
                     └─ Cilium Egress Gateway SNATs the pod to 10.2.0.2 and sends it out wg-proton
```

- Three gateway nodes, one Proton config each: `hp-elite-gen13`, `mini-pc-dell-ultra-worker`, `hp-elite-gen12`.
- The `vpn-gateway` DaemonSet runs in the host network of those nodes.
  It creates the kernel WireGuard link `wg-proton` from the node's Proton config.
- A `CiliumEgressGatewayPolicy` sends matched pod traffic to one of the three gateways.
  Cilium assigns each pod to a gateway by a hash of its endpoint UID, so load spreads across the three.
- The gateway pod sets the node label `egress.vanillax.dev/vpn-ready=true` only while a probe through the tunnel works.
  The policy selects only labelled gateways.

### Kill switch (fail closed)

| Failure | What happens |
|---|---|
| Tunnel stops passing traffic | 3 failed probes (~45 s) remove the label. Pods move to the other gateways. |
| All gateways unready | Cilium drops the matched traffic. It does not fall back to the home IP. |
| Gateway node powers off | A peer gateway removes the label once the Node is `NotReady`. Until then that node's share is dropped. |
| `wg-proton` link deleted or down | Cilium's stale interface drops the traffic. The `ip rule from 10.2.0.2` sends anything else to a blackhole route. |
| Gateway pod stops | It removes its label. The link and the kill switch rule stay in place. |

Sources: Cilium drops traffic when no gateway matches and when no egress IP is set, and skips gateway entries that match no node
([Cilium 1.20 egress gateway docs](https://docs.cilium.io/en/v1.20/network/egress-gateway/egress-gateway/),
`pkg/egressgateway/policy.go` at `v1.20.4`).
Cilium copies Node label changes into the CiliumNode and re-selects gateways (`pkg/node/sync/local_node_sync.go`, `pkg/egressgateway/manager.go`).

### What stays off the VPN

- In-cluster traffic, Service IPs and the LAN: the policy excludes `10.0.0.0/8`, `100.64.0.0/10`, `169.254.0.0/16`, `172.16.0.0/12` and `192.168.0.0/16`.
  That keeps the NAS (`.133`), the Pi (`.15`) and the LB pool direct.
- Host traffic: Talos itself, containerd image pulls and `hostNetwork` pods are not pods to Cilium, so Egress Gateway never touches them.
- Exempt namespaces (phase 2 only), listed below.

### Exempt namespaces

The list lives in `policies/cluster-wide.yaml`. Keep this table in sync with it.

| Namespace | Why |
|---|---|
| `kube-system` | CoreDNS and Cilium must keep working when every tunnel is down. |
| `argocd` | Argo CD must reach GitHub to roll back a broken VPN change. |
| `1passwordconnect`, `external-secrets` | Secrets, including the Proton keys, must sync when the tunnels are down. |
| `vpn-egress` | The gateways themselves. |
| `cloudflared` | The Cloudflare tunnel stays on the home connection by design. |
| `consumers-energy-sync` | Okta asks for step-up MFA from datacenter VPN IPs. |
| `vllm`, `comfyui` | Large public model downloads from huggingface.co; the VPN adds no privacy there and costs speed. |

### Known gaps

- **New pods leak for about a second.** Cilium applies the policy shortly after a pod starts.
  Traffic in that window leaves with the node IP ([Cilium docs](https://docs.cilium.io/en/v1.20/network/egress-gateway/egress-gateway/#delay-for-enforcement-of-egress-policies-on-new-pods)).
  While the Firewalla VPN rule stays on, that traffic still goes through the Firewalla tunnel.
- **DNS** goes pod → CoreDNS → Talos host DNS → Firewalla (`192.168.10.1`), as today. It does not use the Proton tunnel.
- **IPv6:** pods are IPv4-only (`enable-ipv6: false`), and the gateway never configures an IPv6 address.
- **Gateway changes reset connections.** Adding or removing a ready gateway re-hashes pods across gateways,
  which breaks open outbound connections ([cilium/cilium#39245](https://github.com/cilium/cilium/issues/39245)).
- **MTU:** pods send up to 1450-byte packets; `wg-proton` uses 1420. Large uploads may fragment the outer packets. Check upload speed in phase 1.

## Throughput (expected, not measured)

- Each gateway node has a 1 GbE NIC (node-exporter `node_network_speed_bytes`), so one gateway tops out near 940 Mbps.
- One pod uses one gateway, so a single download peaks near 940 Mbps, above today's 670 Mbps cap.
- Many pods spread across three gateways, so the cluster total can reach the 2 Gb line.
- WireGuard crypto runs in kernel softirq on the gateway node. Expect about 1-2 cores per gateway at full speed.

## Options considered

| Option | Verdict | Why |
|---|---|---|
| **Cilium Egress Gateway + kernel WireGuard on gateway nodes** | **Chosen** | Native to our Cilium 1.20.4, cluster-wide by selector, fails closed, multiple gateways spread load. Cilium 1.20 redirects to the policy's `interface` (`bpf/bpf_overlay.c`); [cilium/cilium#40406](https://github.com/cilium/cilium/issues/40406) shows the policy-routing fallback we also install. Works on Talos ([siderolabs/talos#12054](https://github.com/siderolabs/talos/issues/12054)). |
| pod-gateway (gateway pod + webhook-injected VXLAN client) | Rejected | Each client pod needs `NET_ADMIN`, which Pod Security baseline forbids ([PSS](https://kubernetes.io/docs/concepts/security/pod-security-standards/)). One gateway pod per namespace, no load spreading. Light maintenance: last image [v1.13.0](https://github.com/angelnu/pod-gateway/releases) in May 2025. |
| gluetun sidecar per app | Rejected for cluster-wide | Good kill switch and kernel WireGuard ([gluetun wiki](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/wireguard.md)), but one tunnel and one Proton device per pod, plus `NET_ADMIN` in every app. Still fine for a single app that needs its own exit. |
| Talos `WireguardConfig` on nodes + Cilium routing | Rejected | Talos can create the link at boot ([Talos 1.14 WireguardConfig](https://docs.siderolabs.com/talos/v1.14/reference/configuration/network/wireguardconfig)), but the private key would live in the Omni machine config, not in 1Password. Changes need an Omni template sync. No health signal to Cilium. |

## Rollout

Owner steps are marked **(Mitch)**. Hermes can open the phase 2 PR.

1. **(Mitch) Create three Proton WireGuard configs.** Go to <https://account.protonvpn.com/downloads>, section WireGuard.
   Name them after the nodes. Pick a different nearby server for each one. Turn NetShield, Moderate NAT and NAT-PMP off.
   Download each `.conf`.
2. **(Mitch) Store them in 1Password** (desktop, zsh):

    ```bash
    op item create --vault homelab-prod --category password --title proton-wireguard-egress \
      "hp-elite-gen13[password]=$(base64 -w0 < hp-elite-gen13.conf)" \
      "mini-pc-dell-ultra-worker[password]=$(base64 -w0 < mini-pc-dell-ultra-worker.conf)" \
      "hp-elite-gen12[password]=$(base64 -w0 < hp-elite-gen12.conf)"
    rm hp-elite-gen13.conf mini-pc-dell-ultra-worker.conf hp-elite-gen12.conf
    ```

3. **(Mitch) Firewalla: send the three Proton endpoint IPs to the WAN, not the VPN.**
   Add a route rule for the cluster nodes with each `Endpoint` IP from the configs as the target and "Internet" as the route.
   Give it priority over the existing VPN rule. Without it, the new tunnels run inside the Firewalla tunnel and the router stays the bottleneck.
4. **Merge the PR.** Argo enables Egress Gateway in Cilium, rolls the operator and deploys `vpn-egress`.
5. **(Mitch) Restart the Cilium agents**, one node at a time:

    ```bash
    kubectl -n kube-system rollout restart ds/cilium
    kubectl -n kube-system rollout status ds/cilium --timeout=30m
    kubectl get crd ciliumegressgatewaypolicies.cilium.io
    ```

6. **Check phase 1.** Expected results are in the comments.

    ```bash
    kubectl -n vpn-egress logs -l app=vpn-gateway --prefix | grep healthy                # 3 lines, ip=<Proton exit>
    kubectl get nodes -l egress.vanillax.dev/vpn-ready=true                              # 3 nodes
    kubectl -n kube-system exec ds/cilium -- cilium-dbg bpf egress list                  # probe pod IP -> 10.2.0.2
    kubectl -n vpn-egress-test exec deploy/egress-probe -- curl -s https://ipinfo.io/ip  # a Proton IP
    kubectl -n vpn-egress-test exec deploy/egress-probe -- speedtest-cli --simple        # > 670 Mbps down
    ```

    Kill switch test: unlabel all three gateways and run the probe in the same command.
    The gateways set the label again within one probe interval (15 s).

    ```bash
    kubectl label node hp-elite-gen13 mini-pc-dell-ultra-worker hp-elite-gen12 egress.vanillax.dev/vpn-ready- &&
      kubectl -n vpn-egress-test exec deploy/egress-probe -- curl -s -m 5 https://ipinfo.io/ip; echo "exit=$?"
    # expected: no IP printed, exit=28 (timeout)
    ```

7. **Phase 2 (separate PR).** In `kustomization.yaml`, replace `policies/test.yaml` with `policies/cluster-wide.yaml`.
   After merge, check `cilium-dbg bpf egress list` shows pods from many namespaces, and that an exempt namespace still uses the home path.
8. **(Mitch) Phase 3: retire the Firewalla VPN rule** for the cluster nodes, after a week of phase 2.
   Keeping it is also valid: it then only carries host traffic, exempt namespaces and the new-pod window, and it still blocks those from using the home IP.

## Rollback

- Phase 1 or 2: revert the PR in Git. With no policy, pods route as before. The leftover `wg-proton` link and `ip rule` are unused and go away at the next reboot.
- Do not remove the `vpn-ready` labels to "turn it off". That drops matched traffic; it does not bypass the VPN.
- Phase 3: turn the Firewalla VPN rule back on.

## Add or replace a gateway

Change the node name in all five places in one PR: `daemonset.yaml` (affinity and `GATEWAY_NODES`), `rbac.yaml`, `external-secret.yaml`, and both files in `policies/`.
Add its Proton config to the 1Password item first. Keep at least two gateways ready during the change.
