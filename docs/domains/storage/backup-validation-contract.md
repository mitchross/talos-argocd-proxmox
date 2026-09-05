# Backup validation: references are a graph, not a kind check

`scripts/validate-kopiur-coverage.py` checks the aggregate rendered manifests in
Cluster CI. The offline tests live in `scripts/tests/test_kopiur_coverage.py`.

For a protected, Git-owned PVC, validation follows:

```
SnapshotPolicy source PVC -> PVC dataSourceRef -> same-namespace named Restore
                         -> target.populator -> source.fromPolicy back to that policy
```

Missing Restore objects, cross-namespace pointers, non-populator targets, and
wrong policy names are hard failures. An exempt or unprotected application PVC
cannot hide a dangling Kopiur Restore reference either. Operator-owned direct
`target.pvc` restores and the existing explicitly annotated manual-recovery
exception retain their behavior.

Coverage warnings now include every non-system storage class, including flash,
wired HA, static shares, and future local CSI classes. A retired CNPG label is
not a backup guarantee. Intentional disposable or externally protected volumes
should carry `backup-exempt: "true"` and a qualified reason explaining who owns
recovery. This change does not force all data onto Kopiur or change the existing
warning-only policy for previously uncovered PVCs.

A passing validation means no checked restore link is broken. It does not prove
backup freshness, permissions at runtime, snapshot readability, database
consistency, or recovery time. Warnings remain open decisions. Keep running the
canary and application-level recovery drills.

Run locally:

```sh
python -m unittest discover -s scripts/tests -p test_kopiur_coverage.py -v
python scripts/validate-kopiur-coverage.py /tmp/all-manifests.yaml
```

No cluster changes, PVC migrations, retention changes, or destructive tests are
part of this validation improvement. Rollback is a Git revert of this PR.
