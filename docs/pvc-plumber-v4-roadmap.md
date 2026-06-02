# pvc-plumber v4 Roadmap

pvc-plumber `v4.0.1` is shipped and proven in permissive mode. The v4 migration
campaign is closed.

## Current State

- `24` operator-managed PVCs across `18` namespaces.
- `24/24 DR_COMPLETE` before the full cluster nuke.
- Namespace software gate and PVC fuse labels are the current contract.
- pvc-plumber owns RS/RD wiring; VolSync and Kopia move bytes.
- Redis and PostHog are backup-exempt and disposable.
- CNPG remains native Barman/S3.
- Core pvc-plumber has no Prometheus dependency.

## Remaining Operations

- Clean up retained rollback PVs only with explicit approval.
- Keep routine Kopia maintenance under observation; manual full maintenance is not required.
- Review future Longhorn/storage architecture separately from restore operations.

## Future Work

v5 remains design-only. Do not treat strict mode, an admission webhook, a
backup-truth cache, source gating, `minBackupAge`, or fail-closed rebuild
protection as shipped behavior.

## Related Docs

- [pvc-plumber start here](pvc-plumber-start-here.md)
- [v4 cutover reference](pvc-plumber-v4-cutover.md)
- [v4 migration readiness](pvc-plumber-v4-migration-readiness.md)
- [v5 Kopia-native future](pvc-plumber-v5-kopia-native-future.md)
- [historical roadmap snapshot](archive/pvc-plumber/migration-campaign/pvc-plumber-v4-roadmap-pre-nuke.md)
