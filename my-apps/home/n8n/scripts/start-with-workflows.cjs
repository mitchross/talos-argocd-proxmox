const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn, spawnSync } = require('node:child_process');
const { DatabaseSync } = require('node:sqlite');
const { routeWorkflow, assertNoUnpublishedDrafts, CREDENTIAL } = require('./route-workflows.cjs');

const DATABASE = '/home/node/.n8n/database.sqlite';
const KEY_FILE = '/var/run/litellm/api-key';
const WORKFLOWS = '/opt/repo-workflows';

function readState() {
  if (!fs.existsSync(DATABASE)) return null;
  const db = new DatabaseSync(DATABASE, { readOnly: true });
  try {
    const owner = db.prepare('SELECT id FROM user WHERE roleSlug = ? AND password IS NOT NULL').get('global:owner');
    if (!owner) return null;
    return { owner: owner.id, workflows: db.prepare('SELECT id, name, active, versionId, activeVersionId FROM workflow_entity').all() };
  } catch (error) {
    if (error.message.includes('no such table')) return null;
    throw error;
  } finally { db.close(); }
}

function cli(args, expected) {
  const result = spawnSync('n8n', args, { encoding: 'utf8' });
  // n8n import catches errors without consistently returning a nonzero status.
  if (result.status !== 0 || (expected && !result.stdout.includes(expected))) {
    throw new Error(`n8n ${args[0]} failed; inspect the input schema and deployment version`);
  }
}

function reconcile(state) {
  const key = fs.readFileSync(KEY_FILE, 'utf8').trim();
  if (!key) throw new Error('LiteLLM API key is empty');
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'n8n-gitops-'));
  try {
    let exported = [];
    if (state.workflows.length) {
      const exportPath = path.join(temporary, 'existing.json');
      cli(['export:workflow', '--all', `--output=${exportPath}`]);
      exported = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
    }
    const templates = fs.readdirSync(WORKFLOWS).filter((name) => name.endsWith('.json'))
      .map((name) => JSON.parse(fs.readFileSync(path.join(WORKFLOWS, name), 'utf8')));
    const changes = exported.map(routeWorkflow).filter((item, index) => JSON.stringify(item) !== JSON.stringify(exported[index]));
    for (const template of templates) {
      if (!exported.some((item) => item.id === template.id || item.name === template.name)) {
        changes.push({ ...routeWorkflow(template), active: false });
      }
    }
    assertNoUnpublishedDrafts(state.workflows, changes);
    const credentialsPath = path.join(temporary, 'credentials.json');
    fs.writeFileSync(credentialsPath, JSON.stringify([{
      ...CREDENTIAL, type: 'httpHeaderAuth', data: { name: 'Authorization', value: `Bearer ${key}` },
    }]), { mode: 0o600 });
    cli(['import:credentials', `--input=${credentialsPath}`], 'Successfully imported 1 credential');
    fs.unlinkSync(credentialsPath);

    if (changes.length) {
      const importPath = path.join(temporary, 'workflows.json');
      fs.writeFileSync(importPath, JSON.stringify(changes), { mode: 0o600 });
      cli(['import:workflow', `--input=${importPath}`], 'Successfully imported');
      for (const workflow of changes) {
        if (state.workflows.some((item) => item.id === workflow.id && item.active)) {
          cli(['publish:workflow', `--id=${workflow.id}`]);
        }
      }
      const after = readState();
      for (const workflow of changes) {
        const current = after.workflows.find((item) => item.id === workflow.id);
        const wasActive = state.workflows.some((item) => item.id === workflow.id && item.active);
        if (!current || Boolean(current.active) !== wasActive) throw new Error('Workflow import or activation verification failed');
      }
    }
    console.log(`LiteLLM credential reconciled; ${changes.length} workflow imports`);
  } finally { fs.rmSync(temporary, { recursive: true, force: true }); }
}

async function main() {
  const state = readState();
  if (state) reconcile(state);
  const child = spawn('n8n', ['start'], { stdio: 'inherit' });
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => child.kill(signal));
  child.on('exit', (code) => process.exit(process.exitCode || code || 0));
  if (!state) {
    console.log('Waiting for n8n owner setup before importing inactive repository workflows');
    const timer = setInterval(() => {
      try {
        const ready = readState();
        if (!ready) return;
        clearInterval(timer);
        // Initial onboarding has no active GitOps workflows; subsequent restarts reconcile before startup.
        if (ready.workflows.some((workflow) => workflow.active)) {
          throw new Error('Restart n8n to reconcile existing active workflows before starting schedules');
        }
        reconcile(ready);
      } catch (error) {
        console.error(error.message);
        child.kill('SIGTERM');
        process.exitCode = 1;
      }
    }, 5000);
  }
}

main().catch((error) => { console.error(error.message); process.exit(1); });
