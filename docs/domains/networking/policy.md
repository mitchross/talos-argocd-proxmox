# Cilium network policy boundaries

This page states what the shared Cilium NetworkPolicy allows and what it does not
protect. Read it before you rely on the policy for isolation or add a namespace
NetworkPolicy.

The shared policy stops ordinary pods from reaching private LAN addresses that no
rule lists. It allows broad cluster traffic, internet access, and a short list of
LAN exceptions. It does not isolate apps from one another, and it does not make the
NAS unreachable.

The policy is the `CiliumClusterwideNetworkPolicy` named `default-deny-lan-egress` in
[`block-lan-access.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/networking/cilium/policies/block-lan-access.yaml).

## What the shared policy allows

`endpointSelector: {}` selects every endpoint that Cilium manages, which means every
pod on the pod network. This policy is not a host firewall. Host-network pods and
host-firewall behavior need a separate assessment.

| Direction | Allowed by the shared policy |
| --- | --- |
| Ingress | `cluster`, `host`, and `world` entities |
| Egress to public IPv4 | `0.0.0.0/0` except RFC1918 ranges |
| Egress to cluster | `cluster`, `host`, and `kube-apiserver` entities |
| Egress to LoadBalancer pool | All ports in `192.168.10.32/27` |
| Other private destinations | Only if another applicable allow or exception permits them |

A compromised app that is exposed to the internet can therefore reach other cluster
endpoints and the shared storage exceptions.

Cloudflare Tunnel carries public requests to the external Gateway. Cloudflare Access
is not configured, so each app does its own authentication. Private routes use the
internal Gateway and Technitium DNS. See [Split DNS with Technitium](technitium-vanillax-me-migration.md).

## Private-network exceptions

These are the grants in the shared policy. They are not a list of all effective
access, because other policies can add more.

| Destination | Allowed ports | Purpose |
| --- | --- | --- |
| TrueNAS `192.168.10.133` | TCP 443, 2049, 111, 445, 9000, 30292, 30293; UDP 111 | CSI API, NFS, SMB, RustFS |
| Wyze Bridge `192.168.10.46` | TCP 8554 | Frigate RTSP |
| Threadripper Proxmox `192.168.10.14` | TCP 8006 | Proxmox API |
| Solar monitor `192.168.10.174` | TCP 8080, 9812 | Solar metrics |
| IoT subnet `192.168.101.0/24` | TCP 80, 443 | Smart-plug control |
| LoadBalancer pool `192.168.10.32/27` | All | Service external IP access |

A separate policy, `gateway-egress-technitium-ui`, lets only the gateway envoy
(`reserved:ingress`) reach the Pi `192.168.10.15` on TCP 5380. This serves the
`technitium.vanillax.me` route.

Two limits apply to this table:

- The LoadBalancer exception overlaps the Wyze address. The separate 8554 grant does
  not restrict that address to port 8554 while the broader subnet grant applies.
- The router `192.168.10.1` has no explicit allow. A failed ICMP probe does not prove
  that the policy denies every TCP path.

## Allow policies add together

Allow policies combine. A namespace NetworkPolicy that lists only DNS and an
inference backend cannot remove the internet or cluster access that the shared
policy grants.

Cilium explicit deny rules take precedence over allows. A broad deny can also block
required DNS, API, gateway, backup, or storage traffic. See
[Kubernetes policy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
and [Cilium deny policies](https://docs.cilium.io/en/stable/security/policy/language/#deny-policies).

Per-namespace isolation is proposed work. The manifests do not provide it. The
proposal is an opt-in boundary: exclude the opted-in endpoints from the shared allow,
then declare their actual ingress and egress dependencies. Start with a canary.
Observe both allowed and rejected flows before you change real apps.

## Verify a change

Make policy changes through Git. From the operator workstation, inspect the current
policy and endpoint state:

```bash
kubectl get ciliumclusterwidenetworkpolicy
kubectl get ciliumnetworkpolicy,networkpolicy -A
kubectl -n kube-system get pods -l k8s-app=cilium
```

For an existing test pod with Hubble access configured:

```bash
hubble observe --pod <namespace>/<pod> --verdict DROPPED
```

Test each required connection and one TCP destination that the policy must deny,
from the selected endpoint. Use the policy verdicts to tell a denial apart from a
missing route, a DNS failure, a refused connection, or an unavailable server. A
policy object that exists does not prove that it selected the intended endpoint.

## Roll back

If a change breaks required traffic, revert that policy commit. Verify that the
original flows recover.

Keep the Cilium VXLAN configuration that the shed media bridge needs. Transport and
policy are separate controls. [Network topology](topology.md) owns the physical
network and the tunnel.
