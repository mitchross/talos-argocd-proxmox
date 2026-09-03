# SurfSense

Self-hosted SurfSense research platform for the Talos cluster.

## Argo CD boundary

`my-apps/ai/surfsense` is one generated Argo CD Application: `my-apps-surfsense`. Internal `app/`, `postgres/`, `redis/`, and `kopiur/` directories are organizational/resource boundaries only; the `my-apps` ApplicationSet discovers only `my-apps/*/*`.

## Deployment shape

- SurfSense `0.0.39`
- PostgreSQL 17 + pgvector with logical replication for Rocicorp Zero
- Redis 8 for Celery/cache
- Rocicorp Zero `1.6.0`
- SurfSense API + Celery worker co-located in one pod so they share one local RWO knowledge/object-store filesystem
- Celery beat, Zero, and frontend run as separate Deployments
- Existing cluster SearXNG reused at `http://searxng.searxng.svc.cluster.local:8080`
- Public single-origin URL: `https://surfsense.vanillax.me`
- OpenSandbox intentionally disabled because upstream's local provider requires a Docker socket, which Talos does not provide

## Sync order

- wave `-1`: ExternalSecret
- wave `0`: PostgreSQL + Redis and storage/restore reconciliation
- wave `1`: SurfSense migration hook
- wave `2`: API + worker, Celery beat, Zero
- wave `3`: frontend

Argo health gating waits for each wave before advancing. Kopiur Restore CRs and restore-before-bind PVCs intentionally reconcile in the same application sync.

## Required 1Password item

Item name: `surfsense`

Fields:

- `secret_key`
- `db_password`
- `zero_admin_password`
- `zero_query_api_key`

## Local AI

SurfSense uses the active in-cluster OpenAI-compatible llama.cpp backend through its
operator-owned global model catalog:

- Base URL: `http://llama-cpp-service.llama-cpp.svc.cluster.local:8080/v1`
- Model: `qwen3.8-27b`
- Config: `global_llm_config.yaml`, mounted at `/app/app/config/global_llm_config.yaml`
- Context budget: 48,000 input + 16,384 output, leaving 1,152 tokens for request/tool overhead inside llama.cpp's 65,536-token window
- Billing tier: `free` — this is local infrastructure, not a metered provider

Initial embeddings use CPU-local `sentence-transformers/all-MiniLM-L6-v2`, so SurfSense does not request a GPU.

## Obsidian / Mink integration

The CachyOS Obsidian client uses `/home/vanillax/.mink` as its vault and the
official SurfSense Obsidian plugin `0.1.0`. Its server URL is
`http://127.0.0.1:18000`, supplied by the enabled user unit
`~/.config/systemd/user/surfsense-obsidian-tunnel.service`, which maintains an
authenticated `kubectl port-forward` to the backend Service. The plugin targets
workspace `My Workspace`, includes only the `wiki/` folder, leaves attachments
disabled, and reconciles every 10 minutes in addition to realtime note events.

The backend already serves the plugin API beneath `/api/v1/obsidian/*`; no
server-side vault mount belongs in this deployment. Enable API access for the
workspace and create a dedicated personal access token in SurfSense before
configuring the plugin. The token lives only in the plugin's local `data.json`
and must remain excluded from Mink's Git sync. Keep note sync on the loopback
tunnel: plugin `0.1.0` replays vault create events on every Obsidian startup,
and sending that burst through Cloudflare can produce managed-WAF 403s.

## Self-host billing policy

This deployment does not use SurfSense's hosted credit wallet for local infrastructure. `selfhost.env` is materialized as `surfsense-selfhost-policy` and loaded by the API, worker, Beat, and migration containers.

The policy keeps new-user wallet balance at zero and explicitly disables ETL, crawl, captcha, platform-scrape, and Stripe credit billing. This also keeps Auto mode eligible for the local `billing_tier: free` llama.cpp model instead of treating a default signup credit balance as premium-provider eligibility.

SurfSense upstream defaults new users to a $5 wallet. The versioned `surfsense-credit-policy-v1` Sync hook runs after schema migrations and idempotently resets restored or pre-policy wallet balances before the API, worker, Beat, and Zero start. Its checked-in `scripts/reconcile-credit-policy.sh` is mounted through a hash-suffixed Kustomize-generated ConfigMap, so the executable policy stays out of the Job YAML. A fresh deployment and a restored deployment therefore converge on the same no-credit policy without manual SQL.
