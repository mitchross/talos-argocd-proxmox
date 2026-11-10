# Backup validation contract

This page explains what the CI backup check proves and what it does not prove.
Read it when the check fails or warns on your pull request.

The check is `scripts/validate-kopiur-coverage.py`. Cluster CI runs it on the
rendered manifests of the whole Git repo. It needs no cluster. Its offline
tests are in `scripts/tests/test_kopiur_coverage.py`.

## What the check follows

A backup works only when four objects point at each other correctly. The check
does not stop at "a `Restore` exists". It follows every reference from one
object to the next:

```
SnapshotPolicy source PVC -> PVC dataSourceRef -> same-namespace named Restore
                         -> target.populator -> source.fromPolicy back to that policy
```

In words, for each PVC in Git that has a `SnapshotPolicy`:

1. The `SnapshotPolicy` names the PVC as its source.
2. The PVC's `dataSourceRef` names a `Restore` in the same namespace.
3. That `Restore` uses `target.populator`.
4. That `Restore` has `source.fromPolicy` set to the same `SnapshotPolicy`.

## What fails the check

These conditions are hard failures:

- The `Restore` that a PVC names does not exist.
- A reference points into another namespace.
- The `Restore` target is not a populator.
- The `Restore` names the wrong `SnapshotPolicy`.

A backup-exempt PVC, or a PVC with no backup, also fails if its
`dataSourceRef` names a kopiur `Restore` that does not exist.

Two cases are allowed. The first is a `Restore` that an operator owns and that
writes directly to `target.pvc`. The second is a manual recovery that carries
the explicit exception annotation.

## What only warns

The check warns for every PVC that has no backup and no exemption. The warning
covers every non-system storage class, including flash, wired HA, static
shares, and local CSI classes. A warning does not block the pull request.

A label from the retired CNPG operator does not count as a backup.

If a volume is disposable, or another system protects it, mark it
backup-exempt. Add the label `backup-exempt: "true"` and the annotation
`storage.vanillax.dev/backup-exempt-reason`. Write in the reason who owns
recovery of that data.

## What a pass does not prove

A pass means that no checked reference is broken. It does not prove any of
these:

- that a recent backup exists
- that the mover can read the files at runtime
- that the backup can be read back
- that a restored database is consistent
- how long a recovery takes

Treat each warning as an open decision. Keep running the
[restore canary](../../disaster-recovery.md#the-restore-canary) and the
app-level checks in
[post-restore acceptance](../../disaster-recovery.md#post-restore-acceptance).

## Run it locally

```sh
python -m unittest discover -s scripts/tests -p test_kopiur_coverage.py -v
python scripts/validate-kopiur-coverage.py /tmp/all-manifests.yaml
```

The second command reads one file that holds the rendered manifests of every
app. Both commands only read files. They change nothing in the cluster.
