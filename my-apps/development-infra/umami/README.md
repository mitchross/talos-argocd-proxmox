# Umami analytics

Self-hosted web analytics: our Umami fork (v3.5.0 plus replay previews, page URLs and
hostname-based websites; [mitchross/umami](https://github.com/mitchross/umami), branch `homelab`)
on plain PostgreSQL. Session replay is **on** for every site; heatmaps, browser errors and MCP stay off.

| Reaches | Where |
|---|---|
| Dashboard, login, settings, API | `https://umami.vanillax.me` — internal gateway (LAN) only |
| Collection and replay | `https://ingest-umami.vanillax.me` — public, exact paths only |

The Gateway answers every path on the public host with 404, except `/script.js`, `/api/send`,
`/recorder.js`, `/api/record`, `/api/websites/auto/recorder` and radar's recorder path.

## How a site gets tracked

The analytics injector adds the same tag to every public page: `data-website-id="auto"`. Umami finds the
website whose domain matches the page hostname. If none exists and the host is under
`auto.domains` in `websites.yaml`, Umami creates it with the `defaults` on the first visit.

- **New site:** nothing to do. Add a `websites.yaml` entry only for a nicer name or other settings.
- **Fresh install:** the same file rebuilds every website; IDs come from the domain (UUIDv5).
- **Never tracked:** hosts with `0` in the `$umami_host` map in `infrastructure/networking/analytics-injector/default.conf`.
- **Radar** loads Umami from its own code with a fixed ID, listed in `websites.yaml`.

Umami reads `websites.yaml` (`WEBSITES_CONFIG`) at startup. `mode: create` creates missing
websites and leaves existing ones as the UI set them; nothing is ever deleted. A change to the
file rolls the pod, because the ConfigMap name carries a content hash.

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
4. Leave heatmaps **off**. Replay settings come from `websites.yaml`.

Visitor IPs: Umami reads `cf-connecting-ip` before `x-real-ip` and `x-forwarded-for`,
so `CLIENT_IP_HEADER` stays unset.

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
