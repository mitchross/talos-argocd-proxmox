# Cilium network policy boundaries

**Status:** current policy behavior, reviewed 2026-09-05. This page describes
what the manifests allow and where isolation is still weak.

The shared policy limits ordinary pod egress to unlisted private LAN addresses.
It also permits broad cluster traffic, internet access, and shared exceptions.
It does not isolate applications from one another or make the NAS unreachable.
The owning manifest is
[`block-lan-access.yaml`](https://github.com/mitchross/talos-argocd-proxmox/blob/main/infrastructure/networking/cilium/policies/block-lan-access.yaml).

## Effective shared policy

`endpointSelector: {}` selects all Cilium-managed endpoints. Host-network and
host-firewall behavior needs separate assessment. This is not a host firewall.

| Direction | Allowed by the shared policy |
| --- | --- |
| Ingress | `cluster`, `host`, and `world` entities |
| Egress to public IPv4 | `0.0.0.0/0` except RFC1918 ranges |
| Egress to cluster | `cluster`, `host`, and `kube-apiserver` entities |
| Egress to LoadBalancer pool | All ports in `192.168.10.32/27` |
| Other private destinations | Only if another applicable allow or exception permits them |

A compromised exposed application can therefore reach other cluster endpoints and the
shared storage exceptions. Cloudflare Tunnel carries public
requests to the external Gateway. Cloudflare Access is not configured, so application
authentication stays with each application. Private routes use the internal
Gateway and Technitium DNS.

## Explicit private-network exceptions

These are grants in the shared policy, not a list of all effective access:

| Destination | Allowed ports | Purpose |
| --- | --- | --- |
| TrueNAS `192.168.10.133` | TCP 443, 2049, 111, 445, 9000, 30292, 30293; UDP 111 | CSI API, NFS, SMB, RustFS |
| Wyze Bridge `192.168.10.46` | TCP 8554 | Frigate RTSP |
| Threadripper Proxmox `192.168.10.14` | TCP 8006 | Proxmox API |
| Solar monitor `192.168.10.174` | TCP 8080, 9812 | Solar metrics |
| IoT subnet `192.168.101.0/24` | TCP 80, 443 | Smart-plug control |
| LoadBalancer pool `192.168.10.32/27` | All | Service external IP access |

The LoadBalancer exception overlaps the Wyze address. The separate 8554 grant
does not restrict that address to 8554 while the broader subnet grant applies.
The router `192.168.10.1` has no explicit allow. A failed ICMP
probe does not prove that every TCP path is denied.

## Allow policies add together

A namespace NetworkPolicy that lists only DNS and an inference backend cannot
remove internet or cluster access granted by this shared policy. Allow policies
combine. Cilium explicit deny rules take precedence over allows, but a broad deny can also block required DNS, API, gateway, backup, or storage traffic.
See [Kubernetes policy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
and [Cilium deny policies](https://docs.cilium.io/en/stable/security/policy/language/#deny-policies).

The [architecture audit](../../audits/2026-09-05-architecture-audit.md) proposes
an opt-in namespace boundary. Exclude opted-in endpoints from the shared allow,
then declare their actual ingress and egress dependencies. This is proposed work,
not an isolation guarantee the manifests already provide. Start with a
canary. Observe both allowed and rejected flows before changing real apps.

## Verify a change

From the operator workstation, inspect current policy and endpoint state:

```bash
kubectl get ciliumclusterwidenetworkpolicy
kubectl get ciliumnetworkpolicy,networkpolicy -A
kubectl -n kube-system get pods -l k8s-app=cilium
```

For an existing test pod with Hubble access configured:

```bash
hubble observe --pod <namespace>/<pod> --verdict DROPPED
```

Test each required connection and an intentionally denied TCP destination from
the selected endpoint. Use policy verdicts to distinguish denial from a missing
route, DNS failure, refused connection, or unavailable server. A policy object
that exists does not prove it selected the intended endpoint.

Make policy changes through Git. If a change breaks required traffic, revert
that policy commit and verify the original flows recover. Keep the Cilium
VXLAN configuration the shed media bridge needs. Transport and policy are
separate controls. The [topology guide](topology.md) owns the physical network.
