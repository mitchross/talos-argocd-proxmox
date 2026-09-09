# Keep alert view

Alertmanager sends events to Keep. Critical alerts do not automatically call
Holmes or the local model. `backend.provision.workflows` is deliberately empty;
Holmes remains parked until explicitly enabled for an investigation.

The chart includes a workflow checksum in the backend pod template, so changing
the provisioned list rolls the backend. Keep 0.52.1 removes previously provisioned
workflows at startup when no workflows directory or inline workflow is configured.
See its [provisioning code](https://github.com/keephq/keep/blob/v0.52.1/keep/workflowmanager/workflowstore.py)
and [provisioning guide](https://docs.keephq.dev/deployment/provision/workflow).

After sync, check that the backend rollout completes and `holmes-rca` is absent
from the workflow list. Confirm alerts still arrive. This removes the automatic
trigger; it does not deploy the Holmes console or add an investigation interface.
A Git revert restores the workflow and automatic critical-alert calls.

## Authenticated inference

The existing `llama-cpp-local` provider name is retained so Keep updates its
saved authentication in place on startup. It now uses LiteLLM. The
`keep-litellm` ExternalSecret reads the existing 1Password `litellm/master_key`
into `LITELLM_API_KEY`; Keep 0.52.1's provision parser expands
`$(LITELLM_API_KEY)` before saving the provider. Changing provisioned settings
changes the chart checksum and rolls the backend.
The chart imports the credential with `backend.envFromSecrets`; its
`backend.env` template supports literal values only and drops `valueFrom`.

The provider type remains `vllm`, whose implementation appends
`/v1/completions` to `api_url`; its configured gateway URL therefore ends at
`:4000`. Workflow queries must explicitly select `model: qwen3.8-27b`, since
the upstream provider's default model is unrelated to this deployment. No AI
workflow is enabled by this migration. Separately installed UI providers are
not reconciled by this declaration. The read-only migration audit found only
the provisioned `llama-cpp-local` entry, with no separate UI providers.

After sync, verify `keep-litellm` is Ready, the backend has rolled, and the
retained provider points to LiteLLM. An explicitly requested test workflow
should appear in LiteLLM/Langfuse; provider presence alone does not prove a
successful generation. A Git revert restores the previous provider connection.

A synthetic request against the currently deployed LiteLLM
`/v1/completions` returned HTTP 200 for `qwen3.8-27b`, text `OK.`, and usage
counts. This verifies route/model compatibility, not the pending Keep rollout
or complete tracing delivery. The pinned provider's environment substitution,
Bearer header, and appended request path were also checked with a mock transport.

Sources: [environment expansion](https://github.com/keephq/keep/blob/v0.52.1/keep/parser/parser.py),
[startup provider updates](https://github.com/keephq/keep/blob/v0.52.1/keep/providers/providers_service.py),
[vLLM URL and authorization behavior](https://github.com/keephq/keep/blob/v0.52.1/keep/providers/vllm_provider/vllm_provider.py).
