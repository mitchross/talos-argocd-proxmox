# Perplexica / Vane

The existing OpenAI-compatible provider keeps its stable `llama-cpp-cluster` ID
so saved selections continue working, but routes `qwen3.8-27b` through LiteLLM.
The bootstrap merges the Git-owned provider/search catalog into the persistent
configuration, preserving user preferences and unrelated UI-added providers/search fields. Additional saved providers using either legacy local backend URL are also moved to LiteLLM. It injects the gateway credential
from the namespace-local `perplexica-litellm` External Secret and writes the
configuration with mode 0600. The committed seed intentionally has no credential.

Vane reads the persisted provider configuration; changing only `OPENAI_BASE_URL`
and `OPENAI_API_KEY` would leave the saved endpoint active. Rerunning the init
container updates the persisted key/endpoint on every rollout. Secret rotation
requires a Git-declared pod rollout because the application reads its config at
startup. Local Transformers embeddings and SearXNG remain unchanged.

After rollout, run a search and check its calls in
[AI observability](../../../docs/domains/ai-gpu/ai-observability.md).

## Backup permissions and restore acceptance

The seed creates `config.json` as `0:568` with mode `0600`; the existing
`db.sqlite` is `568:568` with mode `0664`. The backup and restore movers use
UID 0 / GID 568 under the documented
[root-owned data exception](../../../docs/domains/storage/kopiur-mover-permissions.md).
No permission-bypass capabilities or ownership rewrite is required: root owns
the config, and group 568 can read the database. The namespace annotation permits
root movers; it does not change Pod Security Admission or grant capabilities.
On September 10, 2026, both files were readable with **all capabilities dropped**
as `0:568`, and a read-only SQLite `PRAGMA quick_check` returned `ok`.

The application currently runs as root. A restore without privileged ownership
preservation may leave the database owned by root rather than its old UID 568;
this is compatible with the current application. Recheck all file owners and
modes if its runtime identity or file-writing behavior changes: root without
capabilities cannot read another UID's owner-only files.

After the merged settings have synced, use the native
[Snapshot invocation](https://kopiur.home-operations.com/reference/crds/snapshot/)
with `policyRef.name: perplexica-data` and `deletionPolicy: Retain`. Require a
completed, non-partial backup, zero failed files, and a concrete
`status.snapshot.kopiaSnapshotID`; a successful no-change run alone is not a new
restore point.

For an isolated drill, declare a separate
[Restore](https://kopiur.home-operations.com/reference/crds/restore/) through Git,
pin `source.snapshotRef.name` to that successful Snapshot, and use a **new**
`target.pvc` name, `longhorn`, `10Gi`, and `ReadWriteOnce`. Set
`policy.onMissingSnapshot: Fail`, use the same mover identity, and leave the
production PVC and its existing populator Restore untouched. The shared backup
component replaces Restore targets with `populator`, so a drill with
`target.pvc` must be rendered independently of that component.

Acceptance requires `Completed`, a matching resolved Kopia snapshot ID, and
read-only checks on the isolated PVC: parse `config.json` without printing its
contents, confirm expected database tables are present, and require
`sqlite3 -readonly /restore/db.sqlite 'PRAGMA integrity_check;'` to return `ok`.
Check file ownership and readability as the application's UID, too. The existing
application image includes SQLite and Node; no custom recovery image is needed.
Compare hashes against the immutable backup source if retained, rather than an
actively changing production database. Remove only the named drill resources
after recording the result; retain the verified backup. This proves the data
round trip, while an isolated application launch is a separate functional check.
