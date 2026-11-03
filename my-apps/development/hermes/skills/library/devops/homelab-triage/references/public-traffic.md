# Public site traffic: bots vs real visitors

For public `*.vanillax.me` apps (redlib, searxng, geocoder). Layers: Cloudflare edge → gateway-external (Envoy) → Anubis → app with PostHog. Read-only; any fix is a GitOps PR or a user-approved Cloudflare change.

## Access

- Prometheus and Loki: see SKILL.md shared endpoints.
- ClickHouse: `kubectl -n posthog exec -i deploy/clickhouse -- clickhouse-client --readonly 1 -d posthog --format JSONEachRow`.
- Cloudflare MCP (`mcp__cloudflare__search` / `mcp__cloudflare__execute`) from `config.yaml` `mcp_servers.cloudflare`, header `Authorization: "Bearer ${env:CLOUDFLARE_API_TOKEN}"`; token is 1Password `cloudflared-proxmox/api-token` via `hermes-secrets`. It needs **Account Settings Read** with the account included (else 401 "Account token must resolve to exactly one Cloudflare account"), Zone Read, Analytics Read, DNS Read, Zone WAF Read/Edit, Cloudflare Tunnel Read.
- A Cloudflare 403 names the missing permission: pass that name on; never ask for a new token when editing the existing one works. The MCP OAuth login can't finish in the pod; use the bearer-token config and ignore the Connectors "Sign in" prompt.
- Verify edge access: `mcp__cloudflare__execute` with `async () => (await cloudflare.request({method:'GET', path:'/zones', query:{name:'vanillax.me'}})).result[0].plan.name`.

## Queries

- Gateway per app: `sum by (envoy_cluster_name)(increase(envoy_cluster_upstream_rq_total{envoy_cluster_name=~".*<app>.*"}[7d]))`, plus `envoy_cluster_upstream_rq_xx` by class. Anubis DENY counts as 2xx at the gateway.
- Anubis: `sum by (rule,action)(increase(anubis_policy_results{namespace="<ns>"}[7d]))`, `anubis_challenges_issued`, `anubis_challenges_validated`, `anubis_proxied_requests_total` (what reaches the app).
- Loki: `{k8s_namespace_name="<ns>",k8s_container_name="anubis"}`; msgs `explicit deny`, `new challenge issued`, `challenge accepted`. Hyphen keys: `| json msg="msg", ua="user_agent", ip="[\"x-real-ip\"]", rule="check_result.name"`.
- Cloudflare GraphQL: `httpRequests1dGroups` (daily), `httpRequestsAdaptiveGroups` by `clientRequestHTTPHost` (24 h). WAF: `GET /zones/<zone>/rulesets/phases/http_request_firewall_custom/entrypoint`. Tunnels: `GET /accounts/${accountId}/cfd_tunnel?is_deleted=false`.

## Procedure

1. **Volume and trend (Prometheus, 7 d)** with a 1-day `query_range` step.
2. **Who gets challenged (Loki, ~1 d).** Aggregate denies by rule and UA; pull challenge/accept lines raw (limit 5000). Count distinct IPs and how many later passed, /24 prefixes, path type (comment permalink / subreddit / post), UA and Chrome major.
3. **What ran JavaScript (PostHog).** Read sampling env first (redlib: `POSTHOG_SAMPLE_RATE`, `POSTHOG_SERVER_PAGEVIEWS`). Export per event filtered on `JSONExtractString(properties,'$host')`: `distinct_id`, `$ip`, `$os`, `$browser`, `$browser_version`, screen size, `$timezone` vs `$geoip_time_zone`, `$geoip_city_name`, `$pathname`, `$referrer`, `$prev_pageview_duration`, `$prev_pageview_max_scroll_percentage`.
4. **Network owner per IP:** `python3 scripts/ip_owner.py <ips.txt> <cache.json>` (one IP per line; caches `as`, `hosting`, `proxy`, `mobile`).
5. **Classify, then count.**
   - Datacenter fleet: `hosting=true` (DigitalOcean AS14061 common), Linux Chrome, en-US, 1-2 requests per IP, comment permalinks.
   - Residential-proxy fleet: one Chrome version, 1920x1080, browser timezone ≠ GeoIP timezone, no GeoIP city, one pageview, faked `https://www.google.com/` referrer; can sit under consumer ASNs (e.g. AS22773 Cox).
   - Likely human: mixed OS/browser, matching timezone, several pages. "Engaged" = 2+ pageviews, >15 s on a page, or >30% scroll.
6. **Cloudflare edge.** Read existing WAF custom rules, daily zone totals and per-host split. Old redirect-only hostnames (e.g. `libreddit.vanillax.me`) still cost tunnel traffic; a Redirect Rule can answer them at the edge.
7. **Answer the open question.** Grep Anubis paths and PostHog pathnames for the suspected abuse path (long `/r/a+b+c` feeds, settings POSTs, `redirect=` probes) before recommending a code limit.

Report: plain words ("challenge", "pass", "server IPs"). If the user asks "what was the goal again", restate the original question and what each access step was for.

## Pitfalls

- The zone already challenges non-US, datacenter ASNs (14061, 16276, 51167, 24940, 63949, 20473), bot UAs and all of redlib, with the home WAN exempt; a new datacenter-ASN rule is usually redundant.
- Anubis can't match by ASN without Thoth; do ASN rules at Cloudflare.
- Anubis without `ED25519_PRIVATE_KEY_HEX` makes a random key each start, so every restart re-challenges everyone. Fixed keys: 1Password item `anubis` (`<app>_ed25519_key_hex`) via an `optional: true` secretKeyRef.
- Cloudflare Free plan has no `firewallEventsAdaptiveGroups`, so challenged networks aren't visible.
