import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const origin = __ENV.ORIGIN || 'https://radar-practice-prod.vanillax.me';
const mode = __ENV.MODE || 'split';
if (!/^https:\/\/radar-practice-(int|cert|prod|prod-v2)\.vanillax\.me$/.test(origin)) {
  throw new Error('Use a Radar practice origin; this script does not target production Radar.');
}
if (!['split', 'load'].includes(mode)) throw new Error('MODE must be split or load.');
const v1 = new Counter('practice_v1_responses');
const v2 = new Counter('practice_v2_responses');
export const options = {
  scenarios: { exercise: { executor: 'constant-arrival-rate', rate: mode === 'load' ? 30 : 10,
    timeUnit: '1s', duration: mode === 'load' ? '30s' : '100s', preAllocatedVUs: 2, maxVUs: 4 } },
  thresholds: { checks: ['rate==1'], http_req_failed: [{ threshold: 'rate<0.02', abortOnFail: true, delayAbortEval: '10s' }],
    http_req_duration: ['p(95)<1000'] },
};
export default function () {
  const response = http.get(`${origin}${mode === 'load' ? '/api/tropical' : '/practice'}`, {
    timeout: '3s', headers: { 'Cache-Control': 'no-cache' },
  });
  check(response, { 'healthy response': r => r.status === 200,
    'version identity': r => ['v1', 'v2'].includes(r.headers['X-Release-Slot']) });
  if (response.headers['X-Release-Slot'] === 'v1') v1.add(1);
  if (response.headers['X-Release-Slot'] === 'v2') v2.add(1);
}
