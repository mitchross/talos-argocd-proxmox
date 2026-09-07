const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { routeWorkflow, assertNoUnpublishedDrafts, CREDENTIAL } = require('../scripts/route-workflows.cjs');

test('active unpublished draft stops reconciliation before any credential import or workflow publish', async () => {
  const workflow = { id: 'draft', name: 'Draft workflow', active: true, versionId: 'draft-v2', activeVersionId: 'published-v1', nodes: [{
    type: 'n8n-nodes-base.httpRequest', parameters: { url: 'http://vllm-service.vllm.svc.cluster.local:8080/v1/chat/completions' },
  }] };
  const commands = [];
  const errors = [];
  const fakeFs = {
    existsSync: () => true, mkdtempSync: () => '/tmp/n8n-guard-test',
    readFileSync: (filename) => filename.endsWith('api-key') ? 'unit-test-key' : JSON.stringify([workflow]),
    writeFileSync: () => {}, unlinkSync: () => {}, rmSync: () => {}, readdirSync: () => [],
  };
  class Database {
    prepare() { return { get: () => ({ id: 'owner' }), all: () => [workflow] }; }
    close() {}
  }
  const dependencies = {
    'node:fs': fakeFs, 'node:path': path, 'node:os': { tmpdir: () => '/tmp' },
    'node:sqlite': { DatabaseSync: Database },
    'node:child_process': {
      spawnSync: (_executable, args) => { commands.push(args[0]); return { status: 0, stdout: 'Successfully imported 1 credential. Successfully imported 1 workflow.' }; },
      spawn: () => { throw new Error('Server must not start with an unsafe draft'); },
    },
    './route-workflows.cjs': require('../scripts/route-workflows.cjs'),
  };
  await vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../scripts/start-with-workflows.cjs'), 'utf8'), {
    require: (name) => dependencies[name],
    console: { log: () => {}, error: (message) => errors.push(message) },
    process: { exit: () => {} },
  });
  assert.deepEqual(commands, ['export:workflow']);
  assert.ok(errors.some((message) => message.includes('unpublished')));
  assert.equal(workflow.activeVersionId, 'published-v1');
  assert.equal(workflow.versionId, 'draft-v2');
});

test('routes a local request with credential auth while preserving payload, activation and unrelated nodes', () => {
  const original = { id: 'existing', active: true, nodes: [
    { name: 'LLM', type: 'n8n-nodes-base.httpRequest', parameters: {
      url: 'http://vllm-service.vllm.svc.cluster.local:8080/v1/chat/completions',
      jsonBody: '{"model":"qwen3.8-27b","max_tokens":256}',
      headerParameters: { parameters: [{ name: 'Authorization', value: 'old-placeholder' }, { name: 'x-other', value: 'keep' }] },
    } },
    { name: 'Other API', type: 'n8n-nodes-base.httpRequest', parameters: { url: 'https://example.org/api' } },
  ] };
  const routed = routeWorkflow(original);
  assert.equal(routed.active, true);
  assert.equal(routed.nodes[0].parameters.url, 'http://litellm-service.litellm.svc.cluster.local:4000/v1/chat/completions');
  assert.deepEqual(routed.nodes[0].credentials.httpHeaderAuth, CREDENTIAL);
  assert.equal(routed.nodes[0].parameters.jsonBody, original.nodes[0].parameters.jsonBody);
  assert.deepEqual(routed.nodes[0].parameters.headerParameters.parameters, [{ name: 'x-other', value: 'keep' }]);
  assert.deepEqual(routed.nodes[1], original.nodes[1]);
  assert.ok(original.nodes[0].parameters.url.includes('vllm-service'));
  assert.deepEqual(routeWorkflow(routed), routed);
});

test('draft guard applies only to changed active workflows and requires published version identity', () => {
  const draft = { id: 'draft', active: true, versionId: 'v2', activeVersionId: 'v1' };
  assert.doesNotThrow(() => assertNoUnpublishedDrafts([draft], [{ id: 'other' }]));
  assert.doesNotThrow(() => assertNoUnpublishedDrafts([{ ...draft, active: false }], [draft]));
  assert.doesNotThrow(() => assertNoUnpublishedDrafts([{ ...draft, activeVersionId: 'v2' }], [draft]));
  assert.throws(() => assertNoUnpublishedDrafts([draft], [draft]), /unpublished/);
  assert.throws(() => assertNoUnpublishedDrafts([{ id: 'draft', active: true }], [draft]), /unpublished/);
});

test('unknown backend API paths fail for review rather than continuing direct', () => {
  assert.throws(() => routeWorkflow({ id: 'unknown', nodes: [{ type: 'n8n-nodes-base.httpRequest', parameters: {
    url: 'http://vllm-service.vllm.svc.cluster.local:8080/unknown',
  } }] }), /Unsupported local LLM route/);
});

test('foreign provider credentials remain intact and gateway credentials contain no secret value', () => {
  const workflow = { id: 'foreign', active: false, nodes: [{
    type: 'n8n-nodes-base.httpRequest',
    parameters: { url: 'https://api.openai.com/v1/chat/completions', authentication: 'predefinedCredentialType' },
    credentials: { openAiApi: { id: 'existing-provider', name: 'Existing provider' } },
  }] };
  assert.deepEqual(routeWorkflow(workflow), workflow);
  assert.deepEqual(Object.keys(CREDENTIAL).sort(), ['id', 'name']);
});

test('repository workflows evaluate explicit no-thinking payloads with per-workflow trace metadata', () => {
  const directory = path.join(__dirname, '../workflows');
  for (const filename of fs.readdirSync(directory)) {
    const workflow = JSON.parse(fs.readFileSync(path.join(directory, filename), 'utf8'));
    assert.equal(workflow.active, false);
    assert.ok(workflow.id);
    for (const node of workflow.nodes) {
      if (!node.parameters?.url?.includes('litellm-service')) continue;
      const body = node.parameters.jsonBody.slice(3, -2).trim();
      const payload = JSON.parse(new Function('$json', `return (${body});`)({ prompt: 'test', systemPrompt: 'test', listingText: 'test', metricsPayload: 'test' }));
      assert.equal(payload.model, 'qwen3.8-27b');
      assert.deepEqual(payload.chat_template_kwargs, { enable_thinking: false, preserve_thinking: false });
      assert.equal(payload.temperature, 0.7);
      assert.equal(payload.top_p, 0.8);
      assert.equal(payload.top_k, 20);
      assert.equal(payload.min_p, 0);
      assert.equal(payload.presence_penalty, 1.5);
      assert.equal(payload.repetition_penalty, 1);
      assert.ok(payload.metadata.tags.includes('app:n8n'));
      assert.deepEqual(node.credentials.httpHeaderAuth, CREDENTIAL);
    }
  }
});
