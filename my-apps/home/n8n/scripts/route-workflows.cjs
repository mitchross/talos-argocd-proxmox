const GATEWAY = 'http://litellm-service.litellm.svc.cluster.local:4000/v1/chat/completions';
const CREDENTIAL = { id: 'gitopsLiteLLM', name: 'LiteLLM gateway' };

function routeWorkflow(workflow) {
  const result = structuredClone(workflow);
  for (const node of result.nodes || []) {
    const params = node.parameters || {};
    if (node.type !== 'n8n-nodes-base.httpRequest') continue;
    let url;
    try { url = new URL(params.url); } catch { continue; }
    if (!['vllm-service.vllm.svc.cluster.local', 'llama-cpp-service.llama-cpp.svc.cluster.local',
      'litellm-service.litellm.svc.cluster.local'].includes(url.hostname)) continue;
    if (url.pathname !== '/v1/chat/completions') {
      throw new Error(`Unsupported local LLM route in workflow ${workflow.id}; review before startup`);
    }
    params.url = GATEWAY;
    params.authentication = 'genericCredentialType';
    params.genericAuthType = 'httpHeaderAuth';
    if (params.headerParameters?.parameters) {
      params.headerParameters.parameters = params.headerParameters.parameters.filter(
        (header) => header.name?.toLowerCase() !== 'authorization',
      );
    }
    if (params.jsonHeaders) throw new Error(`Review JSON headers in workflow ${workflow.id} before routing`);
    node.credentials = { httpHeaderAuth: CREDENTIAL };
  }
  return result;
}

function assertNoUnpublishedDrafts(workflows, changes) {
  const changedIds = new Set(changes.map((workflow) => workflow.id));
  for (const workflow of workflows) {
    if (!workflow.active || !changedIds.has(workflow.id)) continue;
    if (!workflow.activeVersionId || !workflow.versionId || workflow.activeVersionId !== workflow.versionId) {
      throw new Error(`Active workflow ${workflow.id} has unpublished changes; review its draft before LiteLLM reconciliation`);
    }
  }
}

module.exports = { routeWorkflow, assertNoUnpublishedDrafts, CREDENTIAL };
