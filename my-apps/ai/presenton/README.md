# Presenton

Presentation generation and Mem0 call the authenticated LiteLLM gateway using
`qwen3.8-27b`. CPU embeddings and Pexels image search retain their existing
configuration. `presenton-litellm` reads the gateway key from `litellm/master_key`
in 1Password; credentials never enter the ConfigMap.

The pinned application persists provider settings in SQLite's `provider_settings`
row and mirrors them to `/app_data/userConfig.json`. Environment variables alone
cannot override that state. The `reconcile-llm` init container updates only the
four managed LLM fields before startup, preserving authentication and unrelated
preferences. It also updates the file's recovery copy and sets permissions to
0600. `CAN_CHANGE_KEYS=false` keeps the provider controlled by GitOps.

The existing RWO volume and Recreate strategy ensure reconciliation happens after
the prior process stops. On a fresh volume the script seeds the compatibility
file; upstream migrations create the database. Invalid saved JSON fails startup
instead of discarding configuration. A Git revert must also declare the desired
persisted provider settings; reverting environment variables alone is insufficient.

Validation: `python3 my-apps/ai/presenton/scripts/test_reconcile_llm.py` from the
repository root. After rollout, verify a presentation and its Mem0 calls in the
[AI observability runbook](../../../docs/domains/ai-gpu/ai-observability.md).
