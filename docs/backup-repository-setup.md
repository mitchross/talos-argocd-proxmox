# Backup repository setup

This page describes the storage and credentials behind every backup: the S3
store, the bucket, the keys, and how the keys reach each namespace. Read it when
you build the backend for the first time, or when a backup cannot reach its
storage. You do this setup once. After that, one namespace label gives an app
access.

The Kopia repository is the encrypted backup store. It lives in the `kopiur`
bucket on RustFS, an S3-compatible object store that runs on the NAS. For how a
backup and a restore-before-bind work after this setup, see
[how kopiur backup and restore work](domains/storage/kopiur-backup-architecture.md).

!!! note "Other S3 stores work too"
    This cluster uses [RustFS](https://github.com/rustfs/rustfs) at
    `192.168.10.133:30292`, outside the cluster. Any S3 store works, including
    MinIO, TrueNAS S3, Garage, and Backblaze B2. Only the endpoint and the
    credentials change.

## How the credentials reach a namespace

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

Git holds the references. 1Password holds the secret values. External Secrets
Operator (ESO) reads both and writes a `kopiur-rustfs` Secret into each labeled
namespace.

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

You store one credential in 1Password. ESO copies it into every namespace that
carries the label. No app holds its own S3 configuration.

## Where the manifests are

All four files are in `infrastructure/backup/kopiur/`:

| File | Resource | What it sets up |
|---|---|---|
| `clusterrepository.yaml` | `ClusterRepository cluster-kopia` | The Kopia repository on RustFS `s3://kopiur` |
| `externalsecret.yaml` | `ClusterExternalSecret kopiur-rustfs` | The copy of the credentials into labeled namespaces |
| `volumesnapshotclass.yaml` | `VolumeSnapshotClass longhorn-snapclass` | How Longhorn takes a CSI snapshot for kopiur `copyMethod: Snapshot` |
| `namespace.yaml` | `Namespace kopiur-system` | The namespace for the operator, its `Maintenance` object, and the cluster credentials |

This directory is the kopiur configuration. The kopiur operator is a separate
Helm Application, `core-dependencies/kopiur-operator-app.yaml`.

## One-time setup steps

Steps 1 and 2 are manual work on the NAS and in 1Password. Steps 3 to 5 are
already in Git. Argo CD applies them.

### 1. The S3 side: RustFS on TrueNAS

The S3 store must run outside the cluster, so that it survives the loss of the
cluster. Here it is the RustFS app on TrueNAS. The S3 API is at
`192.168.10.133:30292`. The web console is at port `30293`.

!!! warning
    Point Kubernetes at the API port, `30292`. Do not use the console port.
    Do not give Kubernetes the RustFS root key.

1. Install the RustFS app on TrueNAS. Use its app and root credentials only for
   the first setup and for console administration.
2. In the RustFS console, create the bucket `kopiur`. It holds the Kopia
   repository at the bucket root (`prefix: ""`).
3. Create one workload access key named `homelab-workload`. All Kubernetes S3
   clients use this key.
4. Give the key the allow policy from the
   [RustFS credential runbook](domains/rustfs/credential-runbook.md). The runbook
   has the policy JSON and explains why root and workload keys are separate.
5. Confirm that the key has read and write access on the `kopiur` bucket.
   Without it, the `ClusterRepository` cannot create or connect to the repository.
6. Verify that the key works before you rely on it. See [Rules to keep](#rules-to-keep).

The RustFS console also shows a `postgres-backups` bucket. It holds data from
the retired CNPG operator, and a lifecycle policy expires that data.

### 2. The secret side: 1Password

Put the values in one item, `rustfs`, in the `homelab-prod` vault. The
[credential runbook](domains/rustfs/credential-runbook.md) has the full field list.

| Field | Used as |
|---|---|
| `kopia_password` | `KOPIA_PASSWORD`. It encrypts every backup. |
| `rustfs-workload-access-key` | `AWS_ACCESS_KEY_ID` |
| `rustfs-workload-secret-key` | `AWS_SECRET_ACCESS_KEY` |
| `root-access-key` / `root-secret-key` | TrueNAS app administration only. Workloads never use them. |

!!! danger "Do not lose `kopia_password`"
    Without this password, no backup can be decrypted. Keep it in 1Password.

### 3. The repository CR (in Git, already done)

`infrastructure/backup/kopiur/clusterrepository.yaml` declares the Kopia
repository as a custom resource. The main fields are:

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

Four rules apply to this file:

- Write the endpoint as a bare `host:port`. Do not add `http://` or a trailing slash.
- Keep `tls.disableTls: true`. RustFS serves plain HTTP.
- Give every `secretRef` on this cluster-scoped object an explicit `namespace`.
  The kopiur webhook rejects it otherwise.
- `allowedNamespaces.selector` decides which namespaces may use the repository.
  Any namespace with the label `kopiur.home-operations.com/repo: cluster-kopia`
  may use it. The same label selects the namespaces that receive the
  credentials, so one label gives an app both.

The file also sets `parameters.epoch.minDuration` and a longer
`bootstrap.failurePolicy.activeDeadlineSeconds`. The comments in the file give
the reasons. Do not remove them.

### 4. The credential fan-out (in Git, already done)

`infrastructure/backup/kopiur/externalsecret.yaml` is one
`ClusterExternalSecret` named `kopiur-rustfs`. It creates the `kopiur-rustfs`
Secret in every namespace labeled
`kopiur.home-operations.com/repo: cluster-kopia`. That includes `kopiur-system`,
which needs the credentials for the operator's connection and for `Maintenance`.

```yaml
# the Secret each labeled namespace receives (kopiur-rustfs)
KOPIA_PASSWORD:        <from 1Password: kopia_password>
AWS_ACCESS_KEY_ID:     <from 1Password: rustfs-workload-access-key>
AWS_SECRET_ACCESS_KEY: <from 1Password: rustfs-workload-secret-key>
```

The endpoint, the bucket, and the TLS setting are not in this Secret. They are
on the `ClusterRepository`.

!!! warning "The Secret name and keys must match"
    The Secret must be named `kopiur-rustfs`, the name in the
    `ClusterRepository` fields `auth.secretRef.name` and
    `encryption.passwordSecretRef.name`. It must hold the keys `KOPIA_PASSWORD`,
    `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY`.

This cluster does not use kopiur's credential projection. ESO delivers the
credentials, so the kopiur operator needs no cluster-wide right to write Secrets.

Label a namespace and the Secret appears there.

### 5. The snapshot class

`infrastructure/backup/kopiur/volumesnapshotclass.yaml` defines
`VolumeSnapshotClass longhorn-snapclass`. Its driver is `driver.longhorn.io`,
and it is the default snapshot class of the cluster. kopiur's
`copyMethod: Snapshot` refers to it by name, so every backup needs it. Do not
remove it.

### 6. What happens when the store is down

During restore-before-bind, kopiur raises a backend error when the Kopia
repository is unreachable. It does so before it decides what to do about a
missing backup. The PVC stays `Pending` and never binds as an empty volume.
No admission policy is involved. The full flow is in
[how kopiur backup and restore work, section 4](domains/storage/kopiur-backup-architecture.md#4-restore-before-bind-flow-the-dr-magic).

## Verify the backend

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

Expect the `ClusterRepository` to report a healthy state, the Secret to exist,
`nc` to print `OK`, and at least one `Snapshot` in `Succeeded`.

## Rules to keep

- Register the access key on the S3 server and verify it before any
  destructive rebuild. A key that RustFS does not know blocks every restore,
  even when Git is correct. The
  [DR pre-nuke checklist](disaster-recovery.md#pre-nuke-checklist) includes
  this check.
- Confirm that the workload key has read and write access on the `kopiur`
  bucket. With access to other buckets only, the other S3 clients work while the
  `ClusterRepository` fails to create or connect.
- Keep the Kopia password only in 1Password. One repository and one password
  encrypt every backup, so a leak or a loss affects all of them. This is an
  accepted limit on a LAN. See
  [known limitations](storage-architecture.md#known-limitations-and-non-goals).
- To rotate the keys, follow the
  [credential runbook](domains/rustfs/credential-runbook.md). The order is: new
  key on RustFS, update 1Password, force an ESO refresh, restart the consumers
  that read the keys from environment variables.
