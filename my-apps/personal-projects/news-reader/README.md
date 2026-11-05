# News Reader LLM routing

The `news-digest` Temporal worker sends both article summaries and digest titles
to LiteLLM using `LLM_URL`. Its namespace-local ExternalSecret supplies the
`litellm` item's `master_key` as `LITELLM_API_KEY`. The web UI and RSS/Reddit fetches
do not need this credential.

The pinned worker image has no authentication for its two LLM POSTs.
`scripts/prepare-litellm-auth.py` checks that image's source hash and adds a
Bearer header only to those call sites. An init container uses the same image
to prepare `/app/worker.py` on an emptyDir, and the worker mounts it read-only.
Model, prompts, samplers, token limits, image, and Temporal registration stay
the same. Source drift fails initialization and requires upgrade review.

`kustomizeconfig.yaml` tells Kustomize how to rewrite generated ConfigMap
references inside `WorkerDeployment`. The explicit application namespace keeps
the generated ConfigMap and custom resource in the same namespace, so a script
edit changes the worker template's ConfigMap reference.
The installed controller v1.9.0 computes its build ID from the image prefix
**and the full pod template hash**. These environment, volume, and init-container
changes therefore create a new worker version without changing the application image.

After ArgoCD sync, verify three things. The controller-created Deployment contains the
authenticated overlay and updated URL. Its init container succeeds. An
article-summary or digest-title workflow completes with a LiteLLM and Langfuse trace.
Do not infer success from the `WorkerDeployment` manifest alone. Roll back the
overlay and endpoint together through Git. Remove this compatibility overlay
when the owning application adds native API-key configuration.
