# storage-bench

Scratch namespace for the storage benchmark in #3665. Git holds the namespace, two scratch
StorageClasses, the fio job files and the run script. Hermes creates the scratch PVCs and pods by hand,
so Argo does not track them, and deletes them when a run ends.

- `fio/`: profiles A-E from #3665, the same as the 2026-09-20 NAS run.
- `scripts/run-bench.sh`: runs each profile three times on `/data` and prints one JSON line per run.
- `storage-bench-truenas-ssd`: one copy on the NAS VM's S3700 (path 4).
- `storage-bench-flash-2`: one copy on each `flash` disk (path 5, after #3663 step 1).

Retire it by deleting this directory once #3665 is done. No production volume or setting is touched.
