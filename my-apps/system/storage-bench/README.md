# storage-bench

Scratch namespace for the storage benchmark: #3665 (done) and #3705 (NAS flash paths 9-11). Git holds
the namespace, the fio job files and the run script. Hermes creates the scratch PVCs and pods by hand,
so Argo does not track them, and deletes them when a run ends.

- `fio/`: profiles A-E from #3665, the same as the 2026-09-20 NAS run.
- `scripts/run-bench.sh`: runs each profile three times on `/data` and prints one JSON line per run.

The #3665 scratch StorageClasses are removed. A new run adds the class it needs here.
Retire it by deleting this directory once #3705 is done. No production volume or setting is touched.
