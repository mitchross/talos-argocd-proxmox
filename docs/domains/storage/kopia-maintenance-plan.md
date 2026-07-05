# Kopia Repository Maintenance (kopiur-managed)

kopiur runs repository maintenance for you. There is **no** CronJob to author or
babysit. This doc explains what runs, where, and how to verify it.

For the whole backup/restore picture see
[kopiur backup architecture](kopiur-backup-architecture.md); for the one-time
backend setup see [backup repository setup](../../backup-repository-setup.md).

## How maintenance works

Every `ClusterRepository` with `spec.maintenance.enabled: true` (the **default**)
causes the kopiur operator to create and own a `Maintenance` CR. For
`cluster-kopia` that CR runs in the operator namespace **`kopiur-system`** (the
default; `spec.maintenance.namespace` relocates it). That namespace must be in the
repository's `allowedNamespaces` — it carries the
`kopiur.home-operations.com/repo: cluster-kopia` label, so it gets the
`kopiur-rustfs` creds and is permitted by the tenancy webhook.

The operator launches the maintenance mover Job on a schedule. The `Maintenance`
CR holds an **ownership lease** so two owners never run maintenance against the
same repo concurrently (`takeoverPolicy` defaults to `Never` — never seize a lease
another owner holds).

`clusterrepository.yaml` sets **no** `spec.maintenance` block, so the repo uses the
operator defaults: **quick every 6 h, full daily.** The live `Maintenance` CR
confirms the resolved schedule:

| Run | Cron | Jitter | kopia command |
|---|---|---|---|
| quick | `0 */6 * * *` | `30m` | `kopia maintenance run` (cheap index/log work) |
| full | `0 3 * * *` | `1h` | `kopia maintenance run --full` (content reclamation) |

To override, add a `spec.maintenance.schedule` (with required `quick` and `full`
crons, optional `timezone`) to `clusterrepository.yaml`. Other knobs under
`spec.maintenance`: `enabled`, `mover` (Job pod overrides), `failurePolicy`
(backoff/deadline), `namespace`, `takeoverPolicy`. Verify any field against the
installed CRD before adding it: `kubectl explain clusterrepository.spec.maintenance`.

## Verify

```bash
# the operator-owned Maintenance CR (owner + repo + age):
kubectl get maintenance -A

# resolved schedule + lease/Ready conditions:
kubectl get maintenance cluster-kopia -n kopiur-system -o yaml

# the repository itself is healthy:
kubectl get clusterrepository cluster-kopia -o wide
```

A healthy `Maintenance` shows `LeaseOwned: True` and `Ready: True`. A
`Found too many index blobs` warning is benign epoch churn that quick maintenance
compacts away. Do **not** author a manual full-maintenance Job — the operator runs
`--full` daily.
