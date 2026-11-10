# RustFS credential runbook

This runbook lists the RustFS credentials, where they are stored, and how to
rotate the key that Kubernetes uses. RustFS is the S3-compatible object store on
the NAS. A rotation changes the workload key in 1Password and in the cluster
Secrets. It does not change the root key, the Kopia password, or any bucket data.

## The two kinds of credential

RustFS has two kinds of credential. Keep them separate.

| Credential | Where it is created | Who uses it |
|---|---|---|
| Root (app) credential | The TrueNAS RustFS app settings | A person, for the first setup and for console administration |
| Workload access key | The RustFS console | Kubernetes S3 clients, through External Secrets Operator (ESO) |

!!! warning
    Do not point a Kubernetes workload at the root credential. With the
    workload key, the cluster cannot run RustFS admin operations.

## The 1Password item

All values are in the item `rustfs` in the vault `homelab-prod`. The item needs
these fields:

| Field | Purpose |
| --- | --- |
| `root-access-key` | TrueNAS RustFS app/root access key. Do not use for Kubernetes clients. |
| `root-secret-key` | TrueNAS RustFS app/root secret key. Do not use for Kubernetes clients. |
| `rustfs-workload-access-key` | RustFS console-created workload access key for Kubernetes S3 clients. |
| `rustfs-workload-secret-key` | RustFS console-created workload secret key for Kubernetes S3 clients. |
| `kopia_password` | Kopia repository encryption password. |
| `endpoint` | RustFS S3 endpoint, currently `http://192.168.10.133:30292`. |
| `S3_ENDPOINT` | RustFS S3 endpoint, currently `http://192.168.10.133:30292`. |

## The workload key policy

There is one workload key. Its name in the RustFS console is
`homelab-workload`. It has a broad allow policy:

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

The policy is broad on purpose, because this lab has one operator and one tenant:

- A policy per bucket would repeat the namespace separation that Kubernetes
  RBAC already gives. If the cluster is compromised, the key is compromised in
  both designs.
- A new bucket works at once. A new log, metric, or backup destination cannot
  fail because someone forgot an IAM rule.
- The workload key stays separate from `root-access-key`. Bucket creation,
  bucket deletion, and user management need the root credential in the console.

Tighten the policy in these cases:

- More people or operators get access to the cluster.
- One app misuses a bucket. Give that app its own scoped key. Do not change the
  shared key.
- An audit requires least-privilege documentation.

## Which Secrets read the workload key

These ExternalSecrets in Git read `rustfs-workload-access-key` and
`rustfs-workload-secret-key`:

| ExternalSecret | Kubernetes Secret |
| --- | --- |
| `loki-stack/loki-s3-credentials` | `loki-s3-credentials` |
| `monitoring/tempo-s3-credentials` | `tempo-s3-credentials` |
| `posthog/posthog-secrets` | `posthog-secrets` |
| `langfuse/langfuse-secrets` | `langfuse-secrets` |
| `rustfs-lifecycle/rustfs-admin-credentials` | `rustfs-admin-credentials` |
| `kopiur/kopiur-rustfs` (ClusterExternalSecret to every namespace labeled `kopiur.home-operations.com/repo: cluster-kopia`) | `kopiur-rustfs` |

The `kopiur-rustfs` ClusterExternalSecret is in
`infrastructure/backup/kopiur/externalsecret.yaml`. It copies the Kopia
repository credentials into every namespace that has a backup.

## Rotate the workload key

### Before you start

- Sign in to the `op` CLI with access to the `homelab-prod` vault.
- Create the new access key in the RustFS console, with the policy above.
- Keep the new access key and secret key ready to paste. Do not put them in a
  file in Git or in a chat.

### 1. Update 1Password

Replace the two placeholder values by hand, then run the command.

```bash
op item edit rustfs \
  --vault homelab-prod \
  'rustfs-workload-access-key[text]=PASTE_RUSTFS_WORKLOAD_ACCESS_KEY_HERE' \
  'rustfs-workload-secret-key[concealed]=PASTE_RUSTFS_WORKLOAD_SECRET_KEY_HERE'
```

If the item does not have the root fields yet, add them. This step is optional.

```bash
op item edit rustfs \
  --vault homelab-prod \
  'root-access-key[text]=PASTE_RUSTFS_ROOT_ACCESS_KEY_HERE' \
  'root-secret-key[concealed]=PASTE_RUSTFS_ROOT_SECRET_KEY_HERE'
```

### 2. Check the fields

This command shows that the fields exist. It does not reveal concealed values.

```bash
op item get rustfs \
  --vault homelab-prod \
  --fields rustfs-workload-access-key,rustfs-workload-secret-key,kopia_password,endpoint,S3_ENDPOINT
```

Expected result: all five fields are listed.

### 3. Force an ESO refresh

ESO copies the new values into the cluster Secrets. Force the copy now.

```bash
TS="$(date +%s)"
kubectl annotate externalsecret -n loki-stack loki-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n monitoring tempo-s3-credentials force-sync="$TS" --overwrite
kubectl annotate externalsecret -n posthog posthog-secrets force-sync="$TS" --overwrite
kubectl annotate externalsecret -n langfuse langfuse-secrets force-sync="$TS" --overwrite
kubectl annotate externalsecret -n rustfs-lifecycle rustfs-admin-credentials force-sync="$TS" --overwrite

# Also refresh the kopiur repo-credential fanout (one ClusterExternalSecret
# feeds the per-namespace kopiur-rustfs Secret into every backed-up namespace):
kubectl annotate clusterexternalsecret kopiur-rustfs force-sync="$TS" --overwrite
```

Expected result: each command prints that the object is annotated.

### 4. Restart the consumers that read the key from environment variables

A running pod keeps the old environment variables. Restart these workloads.

```bash
kubectl rollout restart statefulset/loki-backend statefulset/loki-write -n loki-stack
kubectl rollout restart deploy/loki-read -n loki-stack
kubectl rollout restart statefulset/tempo -n monitoring
kubectl rollout restart deploy/db deploy/feature-flags deploy/plugins deploy/web deploy/worker \
                       deploy/ingestion-general deploy/ingestion-sessionreplay \
                       deploy/recording-api deploy/replay-capture \
                       deploy/temporal-django-worker deploy/property-defs-rs \
                       -n posthog
kubectl rollout restart deploy/langfuse-web deploy/langfuse-worker -n langfuse
```

Two consumers need no restart:

- A kopiur mover reads the `kopiur-rustfs` Secret of its namespace when kopiur
  creates the Job. The next scheduled or manual `Snapshot` uses the new key. The
  kopiur operator needs no restart.
- The RustFS lifecycle CronJob starts a new Job for each run. The next run uses
  the refreshed Secret.

### Verify

- Check that the restarted pods reach `Running` and stay there.
- Check that the next kopiur `Snapshot` reaches `Succeeded`:
  `kubectl get snapshot -A`.

### Roll back

Put the previous key values back in 1Password with the command in step 1. Then
repeat steps 3 and 4. This works only while the previous key still exists in
RustFS.
