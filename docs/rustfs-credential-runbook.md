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
| `pvc-plumber-access-key` | RustFS console-created workload access key for Kubernetes S3 clients. |
| `pvc-plumber-secret-key` | RustFS console-created workload secret key for Kubernetes S3 clients. |
| `kopia_password` | Kopia repository encryption password. |
| `endpoint` | RustFS S3 endpoint, currently `http://192.168.10.133:30293`. |
| `S3_ENDPOINT` | RustFS S3 endpoint, currently `http://192.168.10.133:30293`. |

Deprecated fields:

| Field | Replacement |
| --- | --- |
| `k8s-admin-access-key` | `pvc-plumber-access-key` |
| `k8s-admin-secret-key` | `pvc-plumber-secret-key` |

Delete the deprecated fields only after all ExternalSecrets are synced to the replacement field names.

## Update 1Password

Use these commands when rotating the RustFS workload key. Replace the placeholder values manually.

```bash
op item edit rustfs \
  --vault homelab-prod \
  'pvc-plumber-access-key[text]=PASTE_RUSTFS_WORKLOAD_ACCESS_KEY_HERE' \
  'pvc-plumber-secret-key[concealed]=PASTE_RUSTFS_WORKLOAD_SECRET_KEY_HERE'
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
  --fields pvc-plumber-access-key,pvc-plumber-secret-key,kopia_password,endpoint,S3_ENDPOINT
```

## ESO Consumers

These GitOps-managed ExternalSecrets read `pvc-plumber-access-key` and `pvc-plumber-secret-key`:

| ExternalSecret | Kubernetes Secret |
| --- | --- |
| `volsync-system/pvc-plumber-kopia` | `pvc-plumber-kopia` |
| `cloudnative-pg/cnpg-s3-credentials` | `cnpg-s3-credentials` |
| `loki-stack/loki-s3-credentials` | `loki-s3-credentials` |
| `monitoring/tempo-s3-credentials` | `tempo-s3-credentials` |
| `posthog/posthog-secrets` | `posthog-secrets` |
| `rustfs-lifecycle/rustfs-admin-credentials` | `rustfs-admin-credentials` |

Force ESO refresh after changing 1Password:

```bash
TS="$(date +%s)"
kubectl annotate externalsecret -n volsync-system pvc-plumber-kopia force-sync="$TS" --overwrite
kubectl annotate externalsecret -n cloudnative-pg cnpg-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n loki-stack loki-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n monitoring tempo-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n posthog posthog-secrets force-sync="$TS" --overwrite
kubectl annotate externalsecret -n rustfs-lifecycle rustfs-admin-credentials force-sync="$TS" --overwrite
```

Restart consumers that load S3 credentials from environment variables:

```bash
kubectl rollout restart deploy/pvc-plumber -n volsync-system
kubectl rollout restart deploy/loki-read statefulset/loki-backend statefulset/loki-write -n loki-stack
kubectl rollout restart statefulset/tempo -n monitoring
kubectl rollout restart deploy/capture deploy/plugins deploy/ingestion-general deploy/ingestion-sessionreplay deploy/recording-api deploy/replay-capture deploy/temporal-django-worker deploy/web deploy/worker -n posthog
```

VolSync mover jobs, CNPG backups, and RustFS lifecycle jobs pick up the new Secret on their next run.
