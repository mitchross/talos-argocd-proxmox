# HolmesGPT inference

Holmes remains parked at zero replicas. Its `local-qwen` model uses
`openai/qwen3.8-27b` through the authenticated LiteLLM gateway. The
`holmes-litellm` ExternalSecret reads the existing 1Password
`litellm/master_key` into `LITELLM_API_KEY`; chart 0.40.0 converts
`envRef:LITELLM_API_KEY` into its runtime environment template and imports the
Secret. The egress policy permits LiteLLM on port 4000.

After GitOps reconciliation, check ExternalSecret readiness and the rendered
model configuration. When Holmes is deliberately enabled, run a read-only
investigation and confirm its request appears in LiteLLM/Langfuse. Rendering
and gateway model discovery do not prove model availability or useful analysis.

The console under `scripts/` and `ui/` remains an undeployed draft. Its fixed
gateway check calls authenticated `/v1/models` and requires `LITELLM_API_KEY`
from the same Secret when eventually deployed. It does not send inference
directly to vLLM. See [console prerequisites](CONSOLE-DESIGN.md).

Revert this migration through Git to restore the previous connection. Keep
the parked replica count until an investigation consumer is explicitly enabled.

References: [chart environment references](https://github.com/robusta-dev/holmesgpt/blob/0.40.0/helm/holmes/values.yaml).
