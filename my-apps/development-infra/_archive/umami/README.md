# Umami analytics

Self-hosted web analytics. Umami 3.5.0 on plain
PostgreSQL (no Redis, ClickHouse or Kafka). Session replay is **on** for every site;
heatmaps, browser errors and MCP stay off.

| Reaches | Where |
|---|---|
| Dashboard, login, settings, API | `https://umami.vanillax.me` — internal gateway (LAN) only |
| Collection and replay | `https://ingest-umami.vanillax.me` — public, exact paths only |

The public host bypasses the injector in the cloudflared config, and the Gateway
answers every path except these with 404: `/script.js`, `/api/send`, `/recorder.js`,
`/api/record`, and `/api/websites/<id>/recorder` for each ID in `scripts/websites.sql`.

The in-cluster injector (`infrastructure/networking/posthog-injector`) adds the
tracker tag to every public HTML page. Each host
maps to a fixed website ID; unknown `*.vanillax.me` hosts go to "Other vanillax.me".
Radar is skipped: it loads Umami itself (radar-ng PR #368) with website ID
`0fc02131-8623-4e19-87ee-25adb67064ee`.

## Add or change a site

1. Add a row with a new UUID to `scripts/websites.sql`.
2. Add the same host and UUID to the `$umami_site` map in the injector's `default.conf`.
3. Add `/api/websites/<uuid>/recorder` (GET and OPTIONS) to `httproute-ingest.yaml`, or replay stays off for that site.
4. Run the injector tests: `python3 -m unittest discover -s infrastructure/networking/posthog-injector/tests -v`.

The PostSync Job `umami-websites` inserts missing rows on every sync. It never
changes or deletes existing rows, so renames in the UI stay.

## Exclude your own visits

Run `localStorage.setItem('umami.disabled', '1')` once in the browser console on each site.
Browsers that send Do Not Track are skipped too.

## Before the pod can start

Two 1Password items, in vault `homelab-prod`:

```bash
# 1. Database password — add a field to the shared postgres-secrets item.
op item edit postgres-secrets --vault homelab-prod "umami_db_password[password]=$(openssl rand -hex 24)"

# 2. Umami's own item: auth secret plus the 2FA encryption key (64 hex chars).
op item create --category password --vault homelab-prod --title umami \
  "app_secret[password]=$(openssl rand -hex 32)" \
  "two_factor_encryption_key[password]=$(openssl rand -hex 32)"
```

Keep both values. A lost `app_secret` logs everyone out; a lost 2FA key breaks
2FA logins. The ExternalSecret `umami-secrets` picks them up within an hour, or
immediately after `kubectl -n external-secrets rollout restart deploy/external-secrets`.

## First-time setup

1. Wait for `umami-postgres` to be Ready and `umami` to pass `/api/heartbeat`
   (the app pod runs `prisma migrate deploy` on start).
2. Open `https://umami.vanillax.me`, log in as `admin` / `umami`.
3. Set a real password immediately, then enable 2FA in Settings → Security.
4. Leave heatmaps **off**. Replay settings come from `scripts/websites.sql`.

## Next phases (separate PRs)

- **Radar** — native Umami events (radar-ng PR #368); drop its PostHog side, PostHog is removed.
  Set `UMAMI_WEBSITE_ID` to the radar row in `scripts/websites.sql`.
- **Visitor IPs** — `CLIENT_IP_HEADER`/`TRUSTED_PROXIES` are deliberately unset. Set them
  from a real request captured through Cloudflare → cloudflared → Gateway first; a guess
  writes wrong IPs silently.

## Known limits (source-verified against the 3.5.0 tag)

- No automatic replay purge on self-hosted Postgres. The CronJob
  `umami-replay-retention` deletes replays older than 30 days, except replays saved in the UI.
- The recorder does not honour `localStorage['umami.disabled']` mid-session, so
  opt-out during a session needs a reload that does not load the scripts.
- `/api/send` accepts payload IP/UA overrides, so public collection data is not
  tamper-proof. Treat it as analytics, not an audit log.
- Keep `/mcp` internal. It is off unless `MCP_ENABLED=1`.

## Storage and backup

Postgres data is 10Gi on `longhorn` (two copies), backed up daily by kopiur with
restore-before-bind. Replays are the largest table (`session_replay`). Check the volume
with `kubectl -n umami exec deploy/umami-postgres -- df -h /var/lib/postgresql/data`.
