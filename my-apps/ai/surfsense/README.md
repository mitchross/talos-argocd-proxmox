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

## Mink Git import

The GitOps manifests define `surfsense-mink-sync`, a six-hourly CronJob that
shallow-clones `mitchross/mink-data` (`main`) and uploads visible Markdown under
`wiki/` into the `Mink` folder in `My Workspace` (ID `1`). Only notes pushed to
GitHub are imported; local-only changes wait for Mink's normal Git sync.
The credentials are provisioned and the CronJob is enabled in Git. Deployment
and first-run verification follow merging this change.
The removed Obsidian plugin and desktop tunnel are not required.

This follows the [Hoyt Labs folder-upload approach](https://github.com/drewpayment/hoytlabs-talos/blob/main/apps/surfsense/minknotes-sync-cronjob.yaml).
[`scripts/sync-mink.py`](scripts/sync-mink.py) is mounted from a hash-suffixed
Kustomize ConfigMap. The job uses temporary node storage, calls `http://backend:8000`
inside the cluster, and uploads at most 500 files per batch. SurfSense identifies
files by folder name and relative path, skips unchanged bytes, and versions edits.
Deleted or renamed source notes are **not pruned**; prior Obsidian imports remain
separate and may duplicate these notes in search. Hidden paths, symlinks, non-Markdown
files, and files outside `wiki/` are excluded.

### Enable and verify

1. The `surfsense` item in 1Password vault `homelab-prod` contains concealed fields
   `mink_github_token` (the existing GitHub CLI OAuth credential, with repository
   access) and `mink_api_token` (the dedicated `Mink Git sync` SurfSense PAT for
   the workspace owner). A replacement GitHub token needs only read-only Contents
   access to `mitchross/mink-data`.
   Enable API access in `My Workspace`. The token must permit document creation
   and reading folders and task logs. The dedicated ExternalSecret keeps these
   credentials separate from the application containers.
2. Merge the enabled [`mink-sync-cronjob.yaml`](mink-sync-cronjob.yaml) through
   the normal GitOps workflow. ArgoCD manages the resources;
   the schedule runs at 00:17, 06:17, 12:17, and 18:17 UTC. Initial processing can
   take hours on CPU; the Job deadline is four hours.
3. Check the credentials and scheduled run:

   ```bash
   kubectl -n surfsense get externalsecret surfsense-mink-sync
   kubectl -n surfsense get cronjob surfsense-mink-sync
   kubectl -n surfsense get jobs --sort-by=.metadata.creationTimestamp
   kubectl -n surfsense logs job/<scheduled-job-name>
   ```

   Expect `SecretSynced`, an unsuspended CronJob, and a completed Job whose final
   line is `Mink import complete`. Check the `Mink/wiki` tree in SurfSense and
   search for a known note to confirm retrieval. A repeat run should retain the
   same folder and documents while skipping unchanged files.

The uploader waits for a **new worker task log to complete**, including the final
batch; an idle folder flag alone can mean the worker has not started. It fails on
partial indexing errors, ambiguous concurrent folder-upload logs, authentication
errors, and timeouts. Avoid other folder uploads in this workspace during a run:
SurfSense 0.0.39 does not return the worker task ID from this endpoint. HTTP reads
retry transient failures; uploads and failed Jobs do not automatically retry because
the server may already have accepted the request. Inspect SurfSense task logs and
wait for any outstanding worker before the next run.

Operator credential bootstrap is recorded in
[`scripts/provision-mink-credentials.py`](scripts/provision-mink-credentials.py).
Run it locally with authenticated `op`, `gh`, and `kubectl` access. It preserves
existing item fields, verifies GitHub access, saves concealed tokens through stdin,
and registers only the SurfSense token hash in the app database for workspace 1's
active owner. This is an administrative account-data operation; it does not change
Kubernetes resources. Re-running reuses the stored token without revoking other
PATs. Expiry follows `PAT_MAX_EXPIRY_DAYS` when configured; otherwise it has no
expiry, matching the deployment default. Revoke `Mink Git sync` in SurfSense to
remove its access; never print the 1Password values in logs.

For rollback, commit `suspend: true`; existing imported documents remain available.
Suspension prevents future Jobs and does not cancel a Job already running.
Validate locally with `kustomize build my-apps/ai/surfsense` and
`python -m unittest discover -s my-apps/ai/surfsense/scripts -p 'test_*.py'` (requires `httpx`).

## Self-host billing policy

This deployment does not use SurfSense's hosted credit wallet for local infrastructure. `selfhost.env` is materialized as `surfsense-selfhost-policy` and loaded by the API, worker, Beat, and migration containers.

The policy keeps new-user wallet balance at zero and explicitly disables ETL, crawl, captcha, platform-scrape, and Stripe credit billing. This also keeps Auto mode eligible for the local `billing_tier: free` llama.cpp model instead of treating a default signup credit balance as premium-provider eligibility.

SurfSense upstream defaults new users to a $5 wallet. The versioned `surfsense-credit-policy-v1` Sync hook runs after schema migrations and idempotently resets restored or pre-policy wallet balances before the API, worker, Beat, and Zero start. Its checked-in `scripts/reconcile-credit-policy.sh` is mounted through a hash-suffixed Kustomize-generated ConfigMap, so the executable policy stays out of the Job YAML. A fresh deployment and a restored deployment therefore converge on the same no-credit policy without manual SQL.
