# Langfuse

Self-hosted AI traces and usage analytics for LiteLLM. The canonical setup,
client wiring, verification, and rollback are in
[AI observability](../../../docs/domains/ai-gpu/ai-observability.md).

This application uses the official Langfuse chart with app-owned PostgreSQL,
ClickHouse, and Valkey. No database operator is installed. PostgreSQL and
ClickHouse have hourly kopiur backups and restore-before-bind. Valkey keeps an
AOF across restarts but is backup-exempt: losing its volume can lose pending
jobs. The `langfuse` RustFS bucket must survive alongside the database backups;
PVC backups do not include that bucket.

The `langfuse` 1Password item supplies stable application secrets and the initial
owner/project credentials. Headless initialization creates missing resources;
rotating those fields is not a password-reset or API-key rotation procedure for
an existing database. Keep the salt and encryption key with the backups.

ArgoCD orders namespace/secrets at wave -1, data stores at 0, the bucket/CORS
initialization hook at 1, and Langfuse at 3. Database migration startup probes
allow 15 minutes before liveness can restart the application. The Helm chart's
empty generated app Secret is removed because External Secrets owns all keys.

`langfuse.vanillax.me` and `langfuse-s3.vanillax.me` use the internal gateway.
The S3 route exposes only this bucket's media/export paths and preserves the
signed Host header. Event/export writes use the RustFS LAN endpoint. Media and
presigned downloads use HTTPS so a browser can reach them without mixed-content
errors; bucket CORS permits the Langfuse origin. Authentication still requires
valid S3 signatures.

The manifests are prepared for GitOps rollout. After merge, confirm both
ExternalSecret readiness and the bucket hook before testing trace ingestion.
See the canonical runbook for the end-to-end checks; rendering alone does not
prove that a deployed request reaches ClickHouse or that recovery succeeds.
