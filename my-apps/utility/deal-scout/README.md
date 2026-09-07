# Deal Scout LLM routing

The dashboard's `DIGEST_LLM_URL` targets LiteLLM. Its namespace-local
ExternalSecret maps the `litellm` item's `master_key` to `LITELLM_API_KEY`.
The pinned dashboard image has no authentication setting for this request;
`scripts/prepare-litellm-auth.py` adds a Bearer header to that one call site.
An init container running the same pinned image checks the original source
hash, writes the patched file to an emptyDir, and mounts it read-only over
`/app/app.py`. Neither the image nor its model, prompt, sampler, or token limit
changes. The Temporal scanner worker itself does not call the LLM.

Image upgrades must review and update the source hash/call-site patch, or remove
the overlay when the application supports authentication directly. Unexpected
source changes fail initialization instead of silently sending anonymous calls.

After ArgoCD sync, confirm `prepare-llm-auth` completed, generate a dashboard
digest, and check that it contains LLM prose rather than the best-effort
facts-only fallback. Verify the request reached LiteLLM/Langfuse. Rendering alone
does not prove a successful inference. Roll back the overlay and endpoint
together through Git; removing authentication while keeping LiteLLM causes 401s.
