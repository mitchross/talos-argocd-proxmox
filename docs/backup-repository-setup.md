# Backup repository setup (S3 + Kopia, via kopiur)

This is the one-time backend setup behind the
[backup/restore system](storage-architecture.md). It covers the S3 box, the bucket, the
credentials, and how they fan out to every namespace. You do this once. After
that, a single namespace label does everything.

The kopia repo is a custom resource (`ClusterRepository`). For how backup and
restore flow once the backend is up, see
[kopiur backup architecture](domains/storage/kopiur-backup-architecture.md).

```mermaid
flowchart LR
  accTitle: External Secrets credential fanout
  accDescr: Git supplies references and namespace selectors while 1Password supplies values. External Secrets reads both and creates short-lived Kubernetes Secrets only in labeled namespaces.

  GIT["`Git desired state
  ClusterExternalSecret
  remote key references`"]
  VAULT["`1Password
  secret values`"]
  ESO["`External Secrets Operator
  reads references
  reconciles continuously`"]

  subgraph NAMESPACES["ONLY LABELED NAMESPACES"]
    direction TB
    NSA["`namespace A
    kopiur-rustfs Secret`"]
    NSB["`namespace B
    kopiur-rustfs Secret`"]
    NSN["`namespace N
    kopiur-rustfs Secret`"]
  end

  GIT refs@--> ESO
  VAULT values@--> ESO
  ESO fanoutA@--> NSA
  ESO fanoutB@--> NSB
  ESO fanoutN@--> NSN

  classDef desired fill:#e1f3e8,stroke:#7bc397,color:#17212b
  classDef secret fill:#fde8e8,stroke:#dc8c8c,color:#17212b
  classDef controller fill:#dff4f6,stroke:#70bcc4,color:#17212b
  class GIT desired
  class VAULT secret
  class ESO controller
  class NSA,NSB,NSN secret

  refs@{ animation: fast }
  values@{ animation: fast }
  fanoutA@{ animation: slow }
  fanoutB@{ animation: slow }
  fanoutN@{ animation: slow }
```

Git owns the references; 1Password owns the values; External Secrets owns the
namespace copies.

> This cluster uses [RustFS](https://github.com/rustfs/rustfs) (an
> S3-compatible object store) running off-cluster at `192.168.10.133:30292`.
> Any S3 works, including MinIO, TrueNAS S3, Garage, and Backblaze B2. Only the endpoint
> and credentials change.

## The credential flow

```text
 1Password item: rustfs
 (kopia_password · accessKey · secretKey)
        │
        ▼
 External Secrets Operator
        │
        ▼
 ClusterExternalSecret  kopiur-rustfs
        │ Secret copy         │ Secret copy
        ▼                     ▼
 namespace A            namespace B
 (repo=cluster-kopia)   (repo=cluster-kopia)
        │                     │
        └────────┬────────────┘
                 ▼
        kopiur mover Jobs
                 │ kopia
                 ▼
        RustFS S3  (bucket: kopiur)
```

You store one credential once. External Secrets copies it into every namespace
that opts in. Apps never carry S3 config.

## The pieces (all in `infrastructure/backup/kopiur/`)

| File | Resource | What it sets up |
|---|---|---|
| `clusterrepository.yaml` | `ClusterRepository cluster-kopia` | the kopia repo, pointing at RustFS `s3://kopiur` |
| `externalsecret.yaml` | `ClusterExternalSecret kopiur-rustfs` | fans the repo creds into labeled namespaces |
| `volumesnapshotclass.yaml` | `VolumeSnapshotClass longhorn-snapclass` | how CSI takes snapshots (kopiur `copyMethod: Snapshot`) |
| `namespace.yaml` | `Namespace kopiur-system` | operator + managed `Maintenance` + cluster creds live here |

This is the GitOps-managed config for kopiur, not the operator. The operator
is the Helm Application at `core-dependencies/kopiur-operator-app.yaml`.

## One-time setup steps

### 1. The S3 side: RustFS on TrueNAS

The S3 store must live **outside the cluster**, so it survives the cluster.
Here it is [RustFS](https://github.com/rustfs/rustfs)
running as a TrueNAS app on the NAS. The S3 API endpoint is
`192.168.10.133:30292` and the console is on `:30293`. **Point Kubernetes at the
API port, not the console.**

1. Install the RustFS app on TrueNAS. Its app and root credentials exist only
   for bootstrap and console administration. **Never point Kubernetes at
   the root key.**
2. In the RustFS console, create the buckets:
   - `kopiur` is the Kopia repository for kopiur (this doc). The repo lives at the
     bucket root, `prefix: ""`.
   - `postgres-backups` is the retired CNPG/Barman bucket, aging out via lifecycle policy.
3. Create one workload access key, named `homelab-workload`, for all
   Kubernetes S3 clients. Scope its allow policy to those buckets.
   The [RustFS credential runbook](domains/rustfs/credential-runbook.md) has the
   exact IAM policy JSON and the root-vs-workload rationale.
   **The workload key MUST have read/write on the `kopiur` bucket.** If the
   policy only scopes it to other buckets, widen it, or the
   `ClusterRepository` create/connect fails.
4. Register the key and verify it works before you rely on it. See the
   rules below.

### 2. The secret side (1Password → ESO)

One item, `rustfs`, in the `homelab-prod` vault. The
[credential runbook](domains/rustfs/credential-runbook.md) has the full field list, including the
admin-only root keys:

| Field | Used as |
|---|---|
| `kopia_password` | `KOPIA_PASSWORD`. It encrypts every backup. **Lose this, lose the backups.** |
| `rustfs-workload-access-key` | `AWS_ACCESS_KEY_ID` |
| `rustfs-workload-secret-key` | `AWS_SECRET_ACCESS_KEY` |
| `root-access-key` / `root-secret-key` | TrueNAS app admin only. Workloads never use them. |

### 3. The repository CR (in Git, already done)

`infrastructure/backup/kopiur/clusterrepository.yaml` declares the repo as a
custom resource. The relevant fields:

```yaml
apiVersion: kopiur.home-operations.com/v1alpha1
kind: ClusterRepository
metadata:
  name: cluster-kopia
spec:
  backend:
    s3:
      bucket: kopiur
      prefix: ""                       # dedicated bucket — repo at the root
      endpoint: 192.168.10.133:30292   # BARE host:port, no scheme/trailing slash
      region: us-east-1
      tls:
        disableTls: true               # RustFS is plain HTTP (LAN-only)
      auth:
        secretRef: { name: kopiur-rustfs, namespace: kopiur-system }
  encryption:
    passwordSecretRef: { name: kopiur-rustfs, namespace: kopiur-system, key: KOPIA_PASSWORD }
  create:
    enabled: true                      # fresh repo at the bucket root
  allowedNamespaces:
    selector:
      matchLabels:
        kopiur.home-operations.com/repo: cluster-kopia
```

Gotchas:
- The endpoint is a **bare `host:port`**, with no `http://` and no trailing slash.
- Plain-HTTP RustFS needs `tls.disableTls: true`.
- A cluster-scoped `secretRef` **must** carry an explicit `namespace`. The webhook enforces this.
- `allowedNamespaces.selector` is label-driven tenancy. Any namespace labeled
  `kopiur.home-operations.com/repo: cluster-kopia` may use this repo. The
  same label drives the credential fan-out below, so onboarding an app is
  one namespace label.

### 4. The credential fan-out (in Git, already done)

`infrastructure/backup/kopiur/externalsecret.yaml` is one
`ClusterExternalSecret kopiur-rustfs`. It creates the `kopiur-rustfs`
Secret in every namespace labeled `kopiur.home-operations.com/repo:
cluster-kopia`. That includes the consumer namespaces and `kopiur-system` itself, which
needs the creds for the controller connection and the managed `Maintenance`:

```yaml
# the Secret each labeled namespace receives (kopiur-rustfs)
KOPIA_PASSWORD:        <from 1Password: kopia_password>
AWS_ACCESS_KEY_ID:     <from 1Password: rustfs-workload-access-key>
AWS_SECRET_ACCESS_KEY: <from 1Password: rustfs-workload-secret-key>
```

The endpoint, bucket, and TLS settings are **not** in this Secret. They live on the
`ClusterRepository` CR. The Secret carries only the creds and the kopia password.

> **The Secret NAME must equal the `ClusterRepository`'s
> `auth.secretRef.name` / `encryption.passwordSecretRef.name` (`kopiur-rustfs`)**
> and carry the well-known keys (`KOPIA_PASSWORD` / `AWS_ACCESS_KEY_ID` /
> `AWS_SECRET_ACCESS_KEY`). This is the "without credential projection" path.
> ESO delivers the creds with least privilege. The operator gets no
> cluster-wide secrets-write RBAC.

Label the namespace and the Secret appears. No app needs its own credential setup.

### 5. The snapshot class

`infrastructure/backup/kopiur/volumesnapshotclass.yaml` defines
`VolumeSnapshotClass longhorn-snapclass` (driver `driver.longhorn.io`, the
cluster-default snapshot class). kopiur's `copyMethod: Snapshot` references it by
name, so every backup depends on it.

### 6. Fail-closed behavior

On a restore-before-bind, if the repo is **unreachable**, kopiur raises a
backend error before it reaches the "no snapshot, bind empty" decision. The
PVC stays `Pending` and never binds an empty volume. There is no separate
admission gate to maintain. Full flow:
[kopiur backup architecture §4 (restore-before-bind)](domains/storage/kopiur-backup-architecture.md).

## Verifying the backend

```bash
# the repository CR is healthy (operator connected/created the repo):
kubectl get clusterrepository cluster-kopia -o wide

# the Secret fans out to a labeled namespace:
kubectl get secret kopiur-rustfs -n <ns>

# the endpoint is reachable from the cluster:
nc -zw5 192.168.10.133 30292 && echo OK

# any completed mover proves auth end-to-end:
kubectl get snapshot -A
```

## Operational rules

- **Register the access key on the S3 server, then verify before any
  destructive rebuild.** An unregistered external credential blocks all
  recovery even with perfect Git state. The
  [DR pre-nuke checklist](disaster-recovery.md#pre-nuke-checklist) checks
  this for you.
- **Confirm the workload key has read/write on the `kopiur` bucket.** A policy
  scoped to another bucket lets everything else look healthy while the
  `ClusterRepository` fails to create or connect.
- **The Kopia password is the single blast radius.** One shared repo, one
  password, every backup encrypted with it. Keep it only in 1Password.
  This is acceptable on a LAN. See
  [known limitations](storage-architecture.md#known-limitations-and-non-goals).
- Rotation. The [credential runbook](domains/rustfs/credential-runbook.md) has the
  per-step procedure: new key on RustFS, update
  1Password, force an ESO refresh, then restart env-var consumers.
