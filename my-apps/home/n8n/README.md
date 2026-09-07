# n8n LLM workflow deployment

The main pod uses `scripts/start-with-workflows.cjs` to import a LiteLLM HTTP
header credential and the three repository workflow templates. The generated
ConfigMaps are mounted by the Helm chart; changing a script or template rolls
the pod. The SQLite PVC and its encryption configuration remain the identity
store. Never delete that configuration while keeping encrypted credentials.

On a fresh installation, complete the normal n8n owner setup in the UI. The
startup supervisor waits for that account and then imports the templates
**inactive**. Configure their other service credentials before enabling their
schedules. The existing deployment was verified to have no owner or workflows
before this change; no account or workflow was created out of band.

On later starts, the supervisor exports existing workflows, changes direct
local HTTP LLM requests to LiteLLM, imports only changed workflows, and republishes
ones that were already active before starting n8n. Unrelated nodes and existing
request bodies are preserved. Existing workflows with a template's ID or name
are retained rather than replaced by the template. Repository templates declare
the no-thinking sampler profile and workflow tags; their token limits and model
remain unchanged.

Before importing any credential or workflow, reconciliation rejects an affected
active workflow if its current draft `versionId` differs from its published
`activeVersionId` (or either ID is missing). It never publishes an unrelated
draft implicitly. A guard failure stops startup and requires review of that
workflow's draft; use a reviewed GitOps rollback to restore the previous startup
behavior, resolve the draft in n8n, then retry the routing change. Unaffected
workflows and inactive drafts do not trigger this guard.

`n8n-litellm` is an ExternalSecret sourced from the `litellm` 1Password item's
`master_key`. The bootstrap mounts the key and imports it as an encrypted
`httpHeaderAuth` credential. Neither main nor worker requires `$env` access for
LLM authentication; `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` is explicit for both.
Workers are disabled in this regular/SQLite deployment. Any future queue-mode
migration must share n8n's database and encryption key with the workers; they
then resolve the same stored credential. After rotating the LiteLLM key, roll
n8n through GitOps to refresh the stored credential.

The CLI import/publish behavior and owner schema were verified against deployed
n8n **2.37.10**. Review this startup integration on n8n upgrades. Import defaults
deactivate workflows, so preserving the active state requires the explicit
publish step before the server starts. Imports require success output because
some CLI errors are caught without a failing exit status.

Validation:

```sh
node --test my-apps/home/n8n/tests/route-workflows.test.cjs
kustomize build --enable-helm my-apps/home/n8n
```

After ArgoCD sync and owner setup, verify the three inactive workflows and
`LiteLLM gateway` credential appear, run an LLM node with test input, and check
its successful execution plus the `app:n8n` workflow tag in Langfuse. A Git
rollback changes the startup behavior but does not undo imported database
records; those can be reviewed and removed through n8n's UI.
