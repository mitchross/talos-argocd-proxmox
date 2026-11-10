# Kopia repository maintenance

This page explains how the Kopia repository gets its maintenance and how to
check that maintenance runs. Maintenance is the Kopia job that compacts indexes
and frees the space of expired backups. kopiur runs it. You do not write or
operate a CronJob for it.

For the whole backup and restore flow, see
[how kopiur backup and restore work](kopiur-backup-architecture.md). For the
one-time storage setup, see [backup repository setup](../../backup-repository-setup.md).

## How maintenance works

The kopiur operator creates and owns a `Maintenance` object for every
`ClusterRepository` that has `spec.maintenance.enabled: true`. That value is the
default. For `cluster-kopia`, the `Maintenance` object lives in the operator
namespace `kopiur-system`. That is also the default, and
`spec.maintenance.namespace` changes it.

The namespace of the `Maintenance` object must be in the repository's
`allowedNamespaces`. `kopiur-system` carries the label
`kopiur.home-operations.com/repo: cluster-kopia` for that reason. The label
gives it the `kopiur-rustfs` credentials and passes the kopiur tenancy webhook.
Do not remove the label.

The operator starts a maintenance mover on a schedule. The `Maintenance` object
holds an ownership lease, so two owners never run maintenance on the same
repository at once. `takeoverPolicy` defaults to `Never`. With `Never`, the
operator does not take a lease that another owner holds.

## The schedule

`infrastructure/backup/kopiur/clusterrepository.yaml` has no `spec.maintenance`
block, so the repository uses the operator defaults:

| Run | Cron | Jitter | Kopia command | What it does |
|---|---|---|---|---|
| quick | `0 */6 * * *` | `30m` | `kopia maintenance run` | Low-cost index and log work |
| full | `0 3 * * *` | `1h` | `kopia maintenance run --full` | Frees the space of expired content |

Quick maintenance runs every 6 hours. Full maintenance runs once a day.

To change the schedule, add `spec.maintenance.schedule` to
`clusterrepository.yaml`. It needs a `quick` cron and a `full` cron, and it
accepts an optional `timezone`. The other fields under `spec.maintenance` are
`enabled`, `mover` (pod overrides for the Job), `failurePolicy` (backoff and
deadline), `namespace`, and `takeoverPolicy`.

Check each field against the installed CRD before you add it:

```bash
kubectl explain clusterrepository.spec.maintenance
```

## Verify

```bash
# the operator-owned Maintenance CR (owner + repo + age):
kubectl get maintenance -A

# resolved schedule + lease/Ready conditions:
kubectl get maintenance cluster-kopia -n kopiur-system -o yaml

# the repository itself is healthy:
kubectl get clusterrepository cluster-kopia -o wide
```

Expect the `Maintenance` object to show `LeaseOwned: True` and `Ready: True`.
The second command also shows the schedule that the operator resolved.

## What goes wrong

- A `Found too many index blobs` warning is harmless. Quick maintenance compacts
  those index blobs.
- Do not write a manual full-maintenance Job. The operator runs `--full` daily.
- Keep `parameters.epoch.minDuration: 6h` in `clusterrepository.yaml`. Kopia
  compacts two epochs behind. With Kopia's 24h default, the index blobs of this
  repository only grow.
- Keep `bootstrap.failurePolicy.activeDeadlineSeconds: 600` in the same file.
  Opening this repository takes about 90 seconds. The 120s default stops the
  connection, kopiur marks the repository `Degraded`, and a `Degraded`
  repository blocks maintenance.
