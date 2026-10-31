# CNPG retirement (plain Postgres + kopiur)

CloudNativePG was retired 2026-08-13; every database now runs as plain
Postgres backed up by kopiur. The per-app cutover steps are in git history
(`git log --follow -- docs/domains/cnpg/plain-postgres-migration.md`). The
current pattern, restore ladder and gotchas are in
[run-postgres-plain-english.md](run-postgres-plain-english.md#the-pattern).

Open item: retire the `postgres-backups` RustFS lifecycle ConfigMap once the
abandoned Barman buckets age out.
