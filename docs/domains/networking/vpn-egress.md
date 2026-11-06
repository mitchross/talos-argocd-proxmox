# Cluster VPN

**Purpose:** send pod internet traffic through Proton using stock tools.
**Status:** staged, routing **off**; live exit-IP and failure tests remain.
**Scope:** phase 1 covers only `vpn-egress-test`. Host traffic and DNS are outside it.

## How it works

- Three single-replica Deployments (`vpn-1`, `vpn-2`, `vpn-3`) run WireGuard on different Linux workers. Placement uses labels, not machine names, and respects existing taints.
- Each uses a separate Proton key from 1Password. Stock `wg-quick` lifecycle commands start and stop the host-network tunnel. No repo-owned runtime scripts, controller or Kubernetes API access.
- The existing Node Feature Discovery (NFD) installation labels tunnel presence as `feature.node.kubernetes.io/vpn-tunnel=1`, `2` or `3`. **Presence is not health.**
- Cilium assigns each selected pod to one tunnel. It spreads pods, not individual connections or one download's bandwidth. LAN and cluster ranges stay direct.
- A Git line switches routing on/off. **All tunnels down while on means blocked internet, not automatic fallback.** Switch off to restore the normal path.

## On and off

In `infrastructure/networking/vpn-egress/kustomization.yaml`, uncomment for **on**;
comment for **off**, then merge the change:

```yaml
components: [./enabled]
```

The switch waits for Argo CD reconciliation. Off removes the policy, not the
tunnels. Existing connections can break when routes change. This PR starts off.
There is no status page, API/Home Assistant switch or custom Grafana dashboard.

## What goes in 1Password

Reuse vault `homelab-prod`, item **`talos-cluster-global-vpn-config`**, fields
**`config-1`**, **`config-2`**, **`config-3`**. Each contains a **base64-encoded**
Proton WireGuard download, not a filename. Use three separate private keys and
three nearby Proton servers. Never use one key in two tunnels.

Each download must have `[Interface]` with `PrivateKey` and
`Address = 10.2.0.2/32`, and one `[Peer]` with `PublicKey` and `Endpoint`.
Use IPv4 endpoint addresses. ExternalSecret checks required fields/address and
assembles the config with `Table = 100`, `MTU = 1420`, IPv4-only
`AllowedIPs = 0.0.0.0/0` and `PersistentKeepalive = 25`. Downloaded DNS and hooks
are discarded; Mitch need not add Table or remove DNS himself.

Secret refresh does not restart a running tunnel. After key rotation, change a
pod annotation in Git to roll **one Deployment at a time**.

## Mitch's Omni step and merge order

1. Add a **cluster-wide configuration patch** in Omni using the full contents of
   [`omni/cluster-template/patches/vpn-egress.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/omni/cluster-template/patches/vpn-egress.yaml).
   Argo CD does not apply it. Do **not** sync the whole fresh-rebuild template
   onto the live cluster. The file is deliberately not attached to that template.
2. Verify both rules on every eligible worker, including replacements:
   priority 1000 routes `from 10.2.0.2/32 lookup 100`; priority 1001 rejects
   that source if table 100 is empty, preventing fallthrough to the LAN default.
   Reserve priorities 1000/1001 and table 100 for this use. `Table = 100` alone
   adds routes, **not** the source rule.
3. Merge this PR **off**. It replaces the paused custom stack and starts the
   three tunnels/test pod. NFD workers roll to host networking. Cilium gets
   `devices: wg-vpn+` and `forceDeviceDetection: true`, preserving LAN auto-detection.
   Once its ConfigMap reconciles, Mitch must restart Cilium agents and wait for
   rollout before enabling routing; this PR does not restart them itself.
4. Check secret sync, three handshakes, three distinct labelled nodes and routing.
   Then merge the one-line **on** change. Widen coverage only in a later PR.

## Verify phase 1

```bash
kubectl -n vpn-egress get externalsecrets,pods -o wide
kubectl get nodes -L feature.node.kubernetes.io/vpn-tunnel
kubectl get ciliumegressgatewaypolicy vpn-egress -o yaml
kubectl -n vpn-egress exec deploy/vpn-1 -- wg show wg-vpn1 latest-handshakes
kubectl -n vpn-egress exec deploy/vpn-1 -- ip -4 rule show
kubectl -n vpn-egress exec deploy/vpn-1 -- ip -4 route get 1.1.1.1 from 10.2.0.2
kubectl -n vpn-egress-test exec deploy/egress-probe -- curl -fsS --max-time 10 https://ipinfo.io/ip
```

Repeat tunnel checks for `vpn-2`/`wg-vpn2` and `vpn-3`/`wg-vpn3`. Expected:
recent handshakes, both Omni rules, route through the tunnel/table 100, and a
Proton exit only after on. Confirm Cilium sees both LAN and tunnel devices.
Test off/on, one unreachable Proton server, drain, abrupt node loss, all-down,
recovery, LAN/cluster access and large uploads. Measure convergence, not assumed
failover times. If Cilium keeps an old interface index after tunnel recreation,
cycle the Git off/on switch. Verify this before widening coverage.

### Phase 2 (separate PR)

Replace `selectors` in `enabled/policy.yaml` with:

```yaml
selectors:
  - podSelector:
      matchExpressions:
        - key: io.kubernetes.pod.namespace
          operator: NotIn
          values: [kube-system, argocd, 1passwordconnect, external-secrets, vpn-egress, cloudflared, consumers-energy-sync, vllm, comfyui]
```

These preserve the earlier exemptions: core services/GitOps/secrets, Cloudflare
Tunnel, energy-provider login and model downloads. Excluded destinations stay
`10.0.0.0/8`, `100.64.0.0/10`, `169.254.0.0/16`, `172.16.0.0/12`, `192.168.0.0/16`.

## Limits and rollback

- Probes restart tunnels after handshakes age beyond about three minutes plus
  failed probes. NFD polls every 60 seconds; it can miss brief link removal or
  retain labels when its worker dies. It is not a health-based failover controller.
- The shared PDB allows one voluntary eviction, not one update across all three
  Deployments. `Recreate` avoids overlapping keys during normal updates, not
  replacement on an unfenced lost node. Stage updates separately; fence lost
  nodes and never force-delete a possibly live gateway.
- Graceful stop runs `wg-quick down`, removing the link/routes. SIGKILL/OOM cannot
  run cleanup; a leftover link can block startup and needs node recovery.
- New pods have Cilium's enforcement delay: this is not a leak-proof privacy
  boundary. DNS and host traffic stay on the normal path. Verify actual router
  encrypted-DNS settings separately. If the router still tunnels cluster traffic,
  Proton endpoints need a WAN exception; do not retire router rules untested.
- Tunnel MTU is 1420; check upload fragmentation/path-MTU behavior in phase 1.

**Rollback:** switch off in Git, verify the policy disappears and normal egress
returns. Revert this PR for the old **paused** stack. Remove the Omni patch only
after routing is off and tunnels have stopped. No router change is in this PR.

## Upstream details that matter

Distinct names `wg-vpn1`–`wg-vpn3` let NFD identify each tunnel without machine
pinning. Three shared `wg0` selectors would all choose the same lexical-first
node, not three gateways ([Cilium v1.20.4 selection](https://github.com/cilium/cilium/blob/v1.20.4/pkg/egressgateway/policy.go),
[CRD](https://github.com/cilium/cilium/blob/v1.20.4/pkg/k8s/apis/cilium.io/client/crds/v2/ciliumegressgatewaypolicies.yaml)).

LinuxServer's normal [startup](https://github.com/linuxserver/docker-wireguard/blob/1.0.20260223-r0-ls129/root/etc/s6-overlay/s6-rc.d/svc-wireguard/run)
deletes the default route on failure—unsafe on a host. Its [shutdown](https://github.com/linuxserver/docker-wireguard/blob/1.0.20260223-r0-ls129/root/etc/s6-overlay/s6-rc.d/svc-wireguard/finish)
does call `wg-quick down`. We instead use stock `sleep` plus direct
`wg-quick up`/`down` lifecycle argv, with one short handshake probe expression.

Verified pins: [LinuxServer 1.0.20260223-r0-ls129](https://github.com/linuxserver/docker-wireguard/releases/tag/1.0.20260223-r0-ls129)
(registry digest pinned), existing [NFD v0.20.1](https://github.com/kubernetes-sigs/node-feature-discovery/releases/tag/v0.20.1)
([`network.virtual`/`name`](https://github.com/kubernetes-sigs/node-feature-discovery/blob/v0.20.1/source/network/network.go),
[worker host `/sys` and networking](https://github.com/kubernetes-sigs/node-feature-discovery/blob/v0.20.1/deployment/helm/node-feature-discovery/templates/worker.yaml)),
[Cilium 1.20](https://docs.cilium.io/en/v1.20/network/egress-gateway/egress-gateway/),
and [Talos 1.14 RoutingRuleConfig](https://docs.siderolabs.com/talos/v1.14/reference/configuration/network/routingruleconfig)
([v1.14.5 validation](https://github.com/siderolabs/talos/blob/v1.14.5/pkg/machinery/config/types/network/routing_rule.go)).
Routing investigation: [cilium#40406](https://github.com/cilium/cilium/issues/40406),
[cilium#43250](https://github.com/cilium/cilium/issues/43250).
