# Cluster VPN

Runbook: [setup, on/off, failure behavior and rollback](../../../docs/domains/networking/vpn-egress.md).

Routing is **off** by default. Uncomment `components: [./enabled]` in
`kustomization.yaml` only after the Omni rules, Cilium agent restart and three
tunnel checks pass. Comment it again to return selected pods to normal egress.
Tunnels stay running while routing is off. Phase 1 covers only `vpn-egress-test`.

Only stock image commands and declarative resources run here. The old custom
controller, scripts, UI and dashboard are removed. All tunnels down while on
means blocked internet; the Git switch is the manual bypass.
