# Deal Scout LLM routing

The dashboard's `DIGEST_LLM_URL` targets LiteLLM. Its namespace-local
ExternalSecret maps the `litellm` item's `master_key` to `LITELLM_API_KEY`,
which the image reads directly and sends as a Bearer token. The Temporal
scanner worker does not call the LLM.

Authentication used to be a source-patching init container here, because the
pinned image had no setting for it. Deal Scout supports the key natively from
v0.13.0, so the overlay is gone; do not reintroduce it.

Without the key the digest silently renders a facts-only summary, so after an
ArgoCD sync generate a dashboard digest and confirm it contains LLM prose, then
verify the request reached LiteLLM/Langfuse. Rendering alone does not prove a
successful inference. `DIGEST_LLM_URL` and the key must move together —
pointing at LiteLLM without a key yields a permanent fallback, not an error.
