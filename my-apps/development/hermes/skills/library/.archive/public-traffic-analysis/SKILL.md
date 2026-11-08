---
name: public-traffic-analysis
description: Tell bots from real visitors on public homelab sites.
version: 1.1.0
author: Hermes
platforms: [linux]
metadata:
  hermes:
    tags: [Homelab, Anubis, PostHog, Cloudflare, Bots, Analytics]
    related_skills: [homelab-ops, homelab-gitops-change-prs]
---

# Public Site Traffic: Bots vs Real Visitors

Splits traffic to a public `*.vanillax.me` app (redlib, searxng, geocoder) into bot fleets and real people. It uses four layers: Cloudflare edge → gateway-external (Envoy) → Anubis → app with PostHog. Read-only: it changes nothing. Any fix ships as a GitOps PR or a Cloudflare change the user approves first.

## When to Use
- "Analyze Anubis / PostHog", "is this abuse or real users", "who uses redlib"
- "Why did traffic triple", "should we rate-limit / block X"
- Before adding a code limit (e.g. a multi-subreddit cap), to check if anyone actually hits that path

## Prerequisites
- In-cluster Prometheus `http://kube-prometheus-stack-prometheus.prometheus-stack.svc:9090` and Loki `http://loki-read.loki-stack.svc:3100` (header `X-Scope-OrgID: 1`).
- `kubectl exec` into `posthog/deploy/clickhouse` (allowed for diagnosis).
- Cloudflare MCP tools `mcp__cloudflare__search` / `mcp__cloudflare__execute`. These come from `config.yaml` `mcp_servers.cloudflare`, with header `Authorization: "Bearer ${env:CLOUDFLARE_API_TOKEN}"`. The token is 1Password `cloudflared-proxmox/api-token`, delivered by `hermes-secrets`. The token needs:
  - **Account Settings Read** (with the account included), or the MCP server answers 401 "Account token must resolve to exactly one Cloudflare account";
  - Zone Read, Analytics Read and DNS Read;
  - Zone WAF Read/Edit for firewall rules;
  - Cloudflare Tunnel Read for tunnels.
- Network-owner lookups use the free ip-api.com batch API. Tell the user the IPs go to a third party.

## How to Run
Run the Prometheus, Loki and ClickHouse queries through the `terminal` tool. Do the counting and classification in `execute_code`: dump raw rows to the scratch dir and count with Python, never by eye. Look up IP owners with `scripts/ip_owner.py` (invoke through the `terminal` tool). Query Cloudflare with `mcp__cloudflare__execute`.

## Quick Reference
- Gateway per app: `sum by (envoy_cluster_name)(increase(envoy_cluster_upstream_rq_total{envoy_cluster_name=~".*<app>.*"}[7d]))`
- Anubis: `sum by (rule,action)(increase(anubis_policy_results{namespace="<ns>"}[7d]))`, `anubis_challenges_issued`, `anubis_challenges_validated`, `anubis_proxied_requests_total`
- Loki stream: `{k8s_namespace_name="<ns>",k8s_container_name="anubis"}`; msgs `explicit deny`, `new challenge issued`, `challenge accepted`
- LogQL json for hyphen keys: `| json msg="msg", ua="user_agent", ip="[\"x-real-ip\"]", rule="check_result.name"`
- ClickHouse: `kubectl -n posthog exec -i deploy/clickhouse -- clickhouse-client --readonly 1 -d posthog --format JSONEachRow`
- Cloudflare GraphQL: `httpRequests1dGroups` (daily requests/threats/uniques), `httpRequestsAdaptiveGroups` by `clientRequestHTTPHost` (per-host, 24 h)
- Cloudflare WAF rules: `GET /zones/<zone>/rulesets/phases/http_request_firewall_custom/entrypoint`
- Tunnels: `GET /accounts/${accountId}/cfd_tunnel?is_deleted=false`

## Procedure
1. **Volume and trend (Prometheus, 7 d).** Gateway totals plus `envoy_cluster_upstream_rq_xx` by code class, and a 1-day `query_range` step for the daily trend. Anubis DENY answers count as 2xx at the gateway. `anubis_proxied_requests_total` is what actually reaches the app.
2. **Who gets challenged (Loki, about 1 day).** Aggregate denies by rule and UA in LogQL. Pull challenge and accept lines raw (`query_range`, limit 5000). Count:
   - distinct IPs, and how many of them later passed;
   - /24 prefixes;
   - path type: comment permalink, subreddit or post;
   - UA and Chrome major version.
3. **What ran JavaScript (PostHog).** First read the app's sampling env (redlib: `POSTHOG_SAMPLE_RATE`, `POSTHOG_SERVER_PAGEVIEWS`), because sampling scales every count. Then export per event, filtered on `JSONExtractString(properties,'$host')`:
   - `distinct_id`, `$ip`, `$os`, `$browser`, `$browser_version`;
   - `$screen_width`/`$screen_height`;
   - `$timezone` vs `$geoip_time_zone`, and `$geoip_city_name`;
   - `$pathname`, `$referrer`;
   - `$prev_pageview_duration`, `$prev_pageview_max_scroll_percentage`.
4. **Network owner per IP.** Run `python3 scripts/ip_owner.py <ips.txt> <cache.json>`. It reads one IP per line and fills the JSON cache with `as`, `hosting`, `proxy` and `mobile`.
5. **Classify, then count.**
   - Datacenter fleet: `hosting=true` (DigitalOcean AS14061 is common). Linux Chrome, en-US, 1-2 requests per IP, comment permalinks.
   - Residential-proxy fleet: one Chrome version, 1920x1080, browser timezone ≠ GeoIP timezone, no GeoIP city, one pageview each, and a faked `https://www.google.com/` referrer. Leased ranges can sit under consumer ISP ASNs (e.g. AS22773 Cox), so don't trust the ASN name.
   - Likely human: mixed OS and browser, matching timezone, several pages. "Engaged" means 2+ pageviews, more than 15 s on a page, or more than 30% scroll.
6. **Cloudflare edge.** Before proposing any firewall rule, read the existing WAF custom rules. Also pull the daily zone totals and the per-host split. Check for old hostnames that only redirect (e.g. `libreddit.vanillax.me`). They still cost tunnel traffic, and a Cloudflare Redirect Rule can answer them at the edge.
7. **Answer the open question.** Grep Anubis paths and PostHog pathnames for the suspected abuse path (long `/r/a+b+c` feeds, settings POSTs, `redirect=` probes) before recommending a code limit.

## Report Shape
Lead with "~N real people a week; the rest is bots". Then one line per group (count, share, behaviour, whether it reaches the app), what this answers, and at most two fixes. Use plain words: "challenge", "pass", "server IPs". If the user asks "what was the goal again", restate the original question, then what each new access step was for.

## Pitfalls
- Check existing Cloudflare WAF rules before suggesting one. The zone already challenges non-US, datacenter ASNs (14061, 16276, 51167, 24940, 63949, 20473), bot UAs and all of redlib, with the home WAN exempt. An "add a DigitalOcean rule" proposal was redundant. Headless fleets pass Cloudflare's managed challenge and Anubis proof-of-work alike, so a passed challenge doesn't mean a human.
- Anubis can't match by ASN without Thoth; do ASN rules at Cloudflare.
- Anubis without `ED25519_PRIVATE_KEY_HEX` makes a random key on each start, so every restart re-challenges everyone. Fixed keys come from 1Password item `anubis` (`<app>_ed25519_key_hex`) via an `optional: true` secretKeyRef.
- Loki keeps about a day of Anubis logs. Use Prometheus for longer windows, and label each number's window.
- Cloudflare Free plan: `firewallEventsAdaptiveGroups` is not available, so you can't see which networks were challenged.
- A 403 from the Cloudflare API names the missing permission. Pass that exact name to the user; never ask them to make a new token when editing the existing one works.
- Cloudflare's MCP OAuth login can't finish inside the pod (it needs a browser callback). Use the bearer-token config, and ignore the Connectors page's "Sign in" prompt.

## Verification
`mcp__cloudflare__execute` with `async () => (await cloudflare.request({method:'GET', path:'/zones', query:{name:'vanillax.me'}})).result[0].plan.name` returns the plan name, which proves edge access. The Prometheus queries return non-empty `anubis_policy_results` for the namespace.
