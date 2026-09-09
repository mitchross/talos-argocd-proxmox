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

### Backup ownership

The Vane image runs as uid 0. The credential-bearing `config.json` is therefore
root-owned mode 0600; the existing SQLite file is uid/gid 568 mode 0664. Both the
SnapshotPolicy and Restore mover use **uid 0, gid 568**, with supplemental group
568 and the namespace's `privileged-movers` annotation. This lets the mover read
the config as its owner and SQLite through its group, while dropping all
capabilities. It does **not** grant access to arbitrary non-root mode-0600 files.
Do not revert the mover to uid 568 while the seed and application still run as
root, or make the API-key-bearing config world-readable.

After rollout, the next scheduled Snapshot must reach `Succeeded` with nonzero
files and include config plus SQLite. Prove recovery using an isolated restore
PVC/application before calling backups fixed. If an upstream image changes its
runtime user or creates differently owned private files, revisit this contract.
Rollback is the previous mover identity; it restores the known backup failure,
so retain the repaired identity unless the runtime ownership is changed too.
