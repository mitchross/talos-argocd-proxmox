# RustFS Credential Runbook

RustFS uses two credential classes:

- Root/app credentials are only for the TrueNAS RustFS app bootstrap and console administration.
- Workload credentials are RustFS-console-created access keys used by Kubernetes clients through External Secrets Operator.

Do not point Kubernetes workloads at the TrueNAS app/root credential.

## 1Password Item

The shared item is `rustfs` in vault `homelab-prod`.

Required fields:

| Field | Purpose |
| --- | --- |
| `root-access-key` | TrueNAS RustFS app/root access key. Do not use for Kubernetes clients. |
| `root-secret-key` | TrueNAS RustFS app/root secret key. Do not use for Kubernetes clients. |
| `rustfs-workload-access-key` | RustFS console-created workload access key for Kubernetes S3 clients. |
| `rustfs-workload-secret-key` | RustFS console-created workload secret key for Kubernetes S3 clients. |
| `kopia_password` | Kopia repository encryption password. |
| `endpoint` | RustFS S3 endpoint, currently `http://192.168.10.133:30292`. |
| `S3_ENDPOINT` | RustFS S3 endpoint, currently `http://192.168.10.133:30292`. |

Deprecated fields:

| Field | Replacement |
| --- | --- |
| `k8s-admin-access-key` | `rustfs-workload-access-key` |
| `k8s-admin-secret-key` | `rustfs-workload-secret-key` |
| `pvc-plumber-access-key` | `rustfs-workload-access-key` (renamed 2026-05-21 with pvc-plumber decommission) |
| `pvc-plumber-secret-key` | `rustfs-workload-secret-key` (renamed 2026-05-21 with pvc-plumber decommission) |

Delete the deprecated fields only after all ExternalSecrets are synced to the replacement field names.

## Workload key IAM policy

The single workload key (named `homelab-workload` in the RustFS console) is
configured with a broad allow policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:*"],
      "Resource": ["arn:aws:s3:::*"]
    }
  ]
}
```

Decision (homelab single-tenant, 2026-05-21): scope is intentionally broad.
Per-bucket IAM scoping would duplicate Kubernetes RBAC's namespace separation
without adding meaningful protection in a single-operator homelab — a
compromised cluster would mean a compromised key either way. Broad policy
also means new buckets work immediately without a forgotten-IAM failure mode
when adding a new logging/metrics/backup destination. Workload key remains
distinct from `root-access-key` so cluster cannot invoke RustFS admin
operations (bucket create/delete, user mgmt — those use root via console).

When to tighten:
- If multiple operators/people gain cluster access and homelab becomes shared.
- If a specific app starts misbehaving with the bucket — scope ITS key, not
  the shared one.
- If running an audit/compliance exercise that requires least-privilege docs.

Captured in mink:
`rustfs-workload-key-policy-full-s3-on-all-buckets-homelab-single-tenant-decision.md`

## Update 1Password

Use these commands when rotating the RustFS workload key. Replace the placeholder values manually.

```bash
op item edit rustfs \
  --vault homelab-prod \
  'rustfs-workload-access-key[text]=PASTE_RUSTFS_WORKLOAD_ACCESS_KEY_HERE' \
  'rustfs-workload-secret-key[concealed]=PASTE_RUSTFS_WORKLOAD_SECRET_KEY_HERE'
```

Optional root/app fields, if the 1Password item does not already have them:

```bash
op item edit rustfs \
  --vault homelab-prod \
  'root-access-key[text]=PASTE_RUSTFS_ROOT_ACCESS_KEY_HERE' \
  'root-secret-key[concealed]=PASTE_RUSTFS_ROOT_SECRET_KEY_HERE'
```

Verify field presence without revealing concealed values:

```bash
op item get rustfs \
  --vault homelab-prod \
  --fields rustfs-workload-access-key,rustfs-workload-secret-key,kopia_password,endpoint,S3_ENDPOINT
```

## ESO Consumers

These GitOps-managed ExternalSecrets read `rustfs-workload-access-key` and `rustfs-workload-secret-key`:

| ExternalSecret | Kubernetes Secret |
| --- | --- |
| `cloudnative-pg/cnpg-s3-credentials` | `cnpg-s3-credentials` |
| `kopia-ui/kopia-ui-secrets` | `kopia-ui-secret` (only consumes `kopia_password`, not the workload key) |
| `loki-stack/loki-s3-credentials` | `loki-s3-credentials` |
| `monitoring/tempo-s3-credentials` | `tempo-s3-credentials` |
| `posthog/posthog-secrets` | `posthog-secrets` |
| `rustfs-lifecycle/rustfs-admin-credentials` | `rustfs-admin-credentials` |
| Each chart-rendered `<ns>/volsync-<pvc>` per backed-up PVC | `volsync-<pvc>` |

The `volsync-system/pvc-plumber-kopia` ExternalSecret was removed
2026-05-21 along with the pvc-plumber operator decommission. Per-PVC
ExternalSecrets are now rendered by the `volsync-backup` Helm chart
at `infrastructure/storage/volsync-backup/` rather than the operator.

Force ESO refresh after changing 1Password:

```bash
TS="$(date +%s)"
kubectl annotate externalsecret -n cloudnative-pg cnpg-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n kopia-ui kopia-ui-secrets force-sync="$TS" --overwrite
kubectl annotate externalsecret -n loki-stack loki-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n monitoring tempo-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n posthog posthog-secrets force-sync="$TS" --overwrite
kubectl annotate externalsecret -n rustfs-lifecycle rustfs-admin-credentials force-sync="$TS" --overwrite

# Also force every chart-rendered per-PVC ES:
kubectl get externalsecret -A -l app.kubernetes.io/managed-by=volsync-backup-chart \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' | \
  while read ns name; do
    [ -z "$ns" ] && continue
    kubectl annotate externalsecret -n "$ns" "$name" force-sync="$TS" --overwrite
  done
```

Restart consumers that load S3 credentials from environment variables:

```bash
# CNPG re-reads cnpg-s3-credentials automatically via the operator's
# Secret-watcher — no restart needed for postgres clusters.
kubectl rollout restart deploy/kopia-ui -n kopia-ui
kubectl rollout restart statefulset/loki-backend statefulset/loki-write -n loki-stack
kubectl rollout restart deploy/loki-read -n loki-stack
kubectl rollout restart statefulset/tempo -n monitoring
kubectl rollout restart deploy/db deploy/feature-flags deploy/plugins deploy/web deploy/worker \
                       deploy/ingestion-general deploy/ingestion-sessionreplay \
                       deploy/recording-api deploy/replay-capture \
                       deploy/temporal-django-worker deploy/property-defs-rs \
                       -n posthog
```

VolSync mover Jobs read the per-PVC Secret at Job creation time, so the
NEXT scheduled (or manually triggered) backup run picks up the new
credentials automatically — no restart of VolSync itself needed.
RustFS lifecycle Job is spawned by its CronJob — next scheduled run
uses the refreshed Secret.
