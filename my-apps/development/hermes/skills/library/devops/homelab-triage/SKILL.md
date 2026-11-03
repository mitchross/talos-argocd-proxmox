---
name: homelab-triage
description: "Use when diagnosing homelab sites, nodes, or bot traffic."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [homelab, triage, DNS, Tailscale, Cloudflare, talos, proxmox, hardware, reboot, thermal, Anubis, PostHog, bots]
    related_skills: [homelab-ops, homelab-gitops-change-prs, fork-hotfix-release, security-advisory-triage]
---

# Homelab live triage

Read-only diagnosis of the live homelab from the Hermes pod.

## When to Use

| Question | Section | Depth |
|---|---|---|
| "Site X won't load" on LAN / Tailscale / phone, browser network errors, Tailscale not routing home | A | `references/network-access.md` |
| "Why did node X reboot", fan speeds, repaste, "any other PCs need a check" | B | `references/node-hardware.md` |
| "Bots or real users?", "why did traffic triple", "should we rate-limit/block X", before adding a code limit | C | `references/public-traffic.md`, `scripts/ip_owner.py` |

Pod, Argo, Longhorn and backup health: `homelab-ops`. A broken fork-built app: `fork-hotfix-release`. Shipping any Git fix: `homelab-gitops-change-prs`.

## Shared endpoints

- Prometheus (no auth): `http://kube-prometheus-stack-prometheus.prometheus-stack.svc:9090` (alias `prometheus-operated.prometheus-stack.svc:9090`). Jobs: `node-exporter` (Talos nodes/VMs; join `node_uname_info` for `nodename`), `physical-node` (Proxmox hosts, Pi, TrueNAS; label `physical_host`).
- Loki: `http://loki-read.loki-stack.svc:3100` with header `X-Scope-OrgID: 1` (without it: `no org id`). Labels `k8s_namespace_name`, `k8s_container_name`, `k8s_pod_name`, `host_name` (node/host logs). Keeps roughly a day of pod logs; use Prometheus for longer windows and label every number with its window.
- Pi (Technitium DNS, Omni, netconsole): reach via `ssh pi` when it works; otherwise hand the user the command.

## Shared rules

- **Read-only.** Diagnose, then propose. Git-owned fixes ship as a GitOps PR; non-Git state (Technitium, Tailscale admin, TrueNAS, Cloudflare, BIOS) changes only after the user says yes, with the effect and the undo stated.
- **Compare against a working peer** (a host of the same route type, a node of the same model) before naming a cause; the difference is usually the cause.
- **Count with code, not by eye**: dump raw rows to the scratch dir and count in Python.
- **When the pod can't reach something**, give one paste-ready read-only command block with a one-line "what this tells me" per part. The user prefers "tell me what to check, I'm SSH'd in" over SSH setup. If pod→host SSH is proposed, use a restricted key (`restrict,from="<lan>",command="<read-only wrapper>"`, dedicated user): a plain key on the Omni Pi is full cluster control.
- **Say a thing once with evidence.** If the user still asks for a safe action (e.g. a rolling restart), do it and report before/after; don't argue twice.
- **Report shape:** verdict first, one table, then 2-3 next actions. Name what was not checked.

## A. Site won't load (split DNS, gateways, Cloudflare, Tailscale)

Layout: `gateway-external` (192.168.10.49) serves public names via cloudflared; `gateway-internal-technitium` (192.168.10.52) serves LAN names, with external-dns writing A records over RFC2136 into Technitium (192.168.10.15, a **Forwarder** zone for `vanillax.me`). Remote devices reach the LAN through the TrueNAS Tailscale app (subnet `192.168.10.0/24`, split DNS `vanillax.me` → 192.168.10.15).

- Order: server side (fast 200 from the pod clears the app) → real browser error code → HTTPRoute `parentRefs` (internal / public / **both**) → DNS by record type A, AAAA **and HTTPS (65)** from both the cluster and Technitium views → public path via `curl --resolve`.
- curl hides HTTP/3 and ECH failures (it never reads the HTTPS record); always read the Chrome error in a real browser.
- Dual-homed hostnames are where split DNS leaks (`ERR_QUIC_PROTOCOL_ERROR`). Restarting cloudflared never changes LAN/Tailscale DNS answers.
- Commands, cause table and the Tailscale exit-node recipe: `references/network-access.md`.

## B. Node reboots, heat, fans, power

- Start with one fleet sweep (uptime, 7-day max CPU/NVMe temp vs crit, throttles, OOM kills, model/BIOS) as one table; flag only real outliers.
- Pin the reboot (boot time + last Loki line), then classify: boot-reason DaemonSet, temps/load/RAM at last-alive, kernel panic/MCE/NVMe lines, pstore, Omni's event log, BIOS power log. Cool + idle + free RAM + no saved panic → power or hardware reset.
- Recommend a repaste only when max temp nears crit or throttle counters rise. Mini PC fans are BIOS-controlled.
- Off-grid solar hosts (hp-shed and its hp-micro VM) reboot by design; one line at most. VMs reboot with their Proxmox host: check the host first.
- Queries, Omni/BIOS log reading, pitfalls and known-harmless noise: `references/node-hardware.md`.

## C. Public site traffic: bots vs real visitors

Four layers: Cloudflare edge → gateway-external (Envoy) → Anubis → app with PostHog. Use Prometheus, Loki, ClickHouse (`kubectl exec` into `posthog/deploy/clickhouse`, read-only) and the Cloudflare MCP tools.

- Read the app's PostHog sampling env first; sampling scales every count.
- A passed challenge (Cloudflare managed or Anubis PoW) doesn't prove a human; headless fleets pass both. Don't trust ASN names either: residential-proxy ranges sit under consumer ISPs.
- Read the existing Cloudflare WAF custom rules before proposing one; the zone already challenges a lot.
- IP-owner lookups go to ip-api.com (third party): tell the user.
- Lead the answer with "~N real people a week; the rest is bots", then one line per group and at most two fixes.
- Queries, classification rules, Cloudflare token permissions and pitfalls: `references/public-traffic.md`. IP owners: `python3 scripts/ip_owner.py <ips.txt> <cache.json>`.
