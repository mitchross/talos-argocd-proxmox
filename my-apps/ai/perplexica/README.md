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
