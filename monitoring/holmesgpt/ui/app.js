'use strict';
const byId = id => document.getElementById(id);
let csrf;
let running = false;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function api(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}
async function refresh() {
  byId('refresh').disabled = true;
  try {
    const state = await api('/api/status');
    byId('status').textContent = `Holmes: ${state.holmes ? 'ready' : 'unavailable'} · Local model: ${state.local_model ? 'ready' : 'unavailable'}${state.upstream_unknown ? ' · Investigation status uncertain: see runbook' : state.busy ? ' · Investigation running' : ''}`;
  } catch (_) {
    byId('status').textContent = 'Console status check failed. This is not evidence the cluster is healthy.';
  } finally { byId('refresh').disabled = false; }
}
byId('refresh').addEventListener('click', refresh);
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
  byId('question').value = button.dataset.question;
  byId('question').focus();
}));
byId('investigate').addEventListener('submit', async event => {
  event.preventDefault();
  if (running) return;
  running = true;
  byId('submit').disabled = true;
  byId('result').hidden = false;
  byId('answer').textContent = '';
  byId('tools').replaceChildren();
  byId('evidence').hidden = true;
  byId('progress').textContent = 'Submitting investigation…';
  try {
    csrf = (await api('/api/session')).csrf;
    const job = await api('/api/investigate', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({question: byId('question').value, namespace: byId('namespace').value.trim(), window: byId('window').value})});
    const started = Date.now();
    while (true) {
      const result = await api(`/api/results/${encodeURIComponent(job.id)}`);
      if (result.state === 'complete') {
        byId('progress').textContent = 'Investigation finished. No resources were changed.';
        byId('answer').textContent = result.analysis;
        for (const tool of result.evidence || []) {
          const item = document.createElement('li');
          item.textContent = `${tool.tool}: ${tool.description}`;
          byId('tools').appendChild(item);
        }
        byId('evidence').hidden = !(result.evidence || []).length;
        break;
      }
      if (result.state === 'failed') throw new Error(result.error);
      byId('progress').textContent = `Gathering evidence and reasoning locally… ${Math.floor((Date.now() - started) / 1000)} seconds elapsed. No need to keep resubmitting.`;
      await sleep(2500);
    }
  } catch (error) {
    byId('progress').textContent = `Investigation not completed: ${error.message}`;
  } finally {
    running = false;
    byId('submit').disabled = false;
    refresh();
  }
});
refresh();
