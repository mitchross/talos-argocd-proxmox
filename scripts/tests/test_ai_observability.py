"""Check the wiring that previously allowed healthy pods with missing telemetry."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return yaml.safe_load((ROOT / path).read_text())


def container(document):
    return document['spec']['template']['spec']['containers'][0]


def environment(document):
    return {entry['name']: entry.get('value') for entry in container(document)['env']}


class AIObservabilityTests(unittest.TestCase):
    def test_langfuse_uses_v4_otel_and_shared_project_credentials(self):
        app = 'my-apps/ai/litellm/'
        config = read(app + 'config.yaml')['litellm_settings']
        self.assertEqual(config['callbacks'], ['prometheus', 'langfuse_otel'])
        self.assertNotIn('success_callback', config)
        self.assertNotIn('failure_callback', config)
        env = environment(read(app + 'deployment.yaml'))
        self.assertEqual(env['LANGFUSE_HOST'], 'http://langfuse-web.langfuse.svc.cluster.local:3000')
        self.assertNotIn('POSTHOG_API_URL', env)
        fields = {x['secretKey']: x['remoteRef'] for x in read(app + 'externalsecret.yaml')['spec']['data']}
        for field in ['PUBLIC', 'SECRET']:
            self.assertEqual(fields['LANGFUSE_' + field + '_KEY'],
                             {'key': 'langfuse', 'property': field.lower() + '-key'})
        self.assertNotIn('POSTHOG_API_KEY', fields)
        # An old Secret must not start the new callback without project credentials.
        deployment = container(read(app + 'deployment.yaml'))
        refs = {x['name']: x.get('valueFrom', {}).get('secretKeyRef') for x in deployment['env']}
        for name in ['LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY']:
            self.assertEqual(refs[name], {'name': 'litellm-secrets', 'key': name})

    def test_metrics_auth_and_webui_use_the_actual_gateway_secret_source(self):
        app = 'my-apps/ai/litellm/'
        config = read(app + 'config.yaml')['litellm_settings']
        self.assertIn('prometheus', config['callbacks'])
        self.assertTrue(config['require_auth_for_metrics_endpoint'])
        self.assertEqual(sorted(set(config['prometheus_latency_buckets'])), config['prometheus_latency_buckets'])
        self.assertGreaterEqual(max(config['prometheus_latency_buckets']), 1800)
        endpoint = read(app + 'servicemonitor.yaml')['spec']['endpoints'][0]
        secret = read(app + 'externalsecret.yaml')
        auth = endpoint['authorization']['credentials']
        self.assertEqual(auth['name'], secret['spec']['target']['name'])
        gateway_key = next(x for x in secret['spec']['data'] if x['secretKey'] == auth['key'])
        webui_secret = read('my-apps/ai/open-webui/externalsecret.yaml')
        self.assertEqual(webui_secret['spec']['data'][0]['remoteRef'], gateway_key['remoteRef'])
        webui = container(read('my-apps/ai/open-webui/deployment.yaml'))
        for item in webui['env']:
            if item['name'] in ['OPENAI_API_KEY', 'OPENAI_API_KEYS']:
                self.assertEqual(item['valueFrom']['secretKeyRef'], {
                    'name': webui_secret['spec']['target']['name'], 'key': 'api-key'})

    def test_config_rollout_and_service_monitor_port_match_after_render(self):
        rendered = subprocess.check_output(['kustomize', 'build', str(ROOT / 'my-apps/ai/litellm')], text=True)
        docs = list(yaml.safe_load_all(rendered))
        deployment = next(d for d in docs if d['kind'] == 'Deployment')
        config = next(d for d in docs if d['kind'] == 'ConfigMap')
        volume = deployment['spec']['template']['spec']['volumes'][0]['configMap']['name']
        self.assertEqual(volume, config['metadata']['name'])
        self.assertRegex(volume, r'^litellm-config-[a-z0-9]+$')
        service = next(d for d in docs if d['kind'] == 'Service')
        monitor = next(d for d in docs if d['kind'] == 'ServiceMonitor')
        for key, value in monitor['spec']['selector']['matchLabels'].items():
            self.assertEqual(service['metadata']['labels'][key], value)
        self.assertIn(monitor['spec']['endpoints'][0]['port'], [p['name'] for p in service['spec']['ports']])

    def test_pi_and_webui_use_gateway_without_changing_backend_context(self):
        guide = (ROOT / 'docs/domains/ai-gpu/pi-agent-local-dev.md').read_text()
        blocks = [json.loads(b) for b in re.findall(r'```json\n(.*?)\n```', guide, re.S)]
        provider = next(b['providers']['vanillax-vllm'] for b in blocks if 'providers' in b)
        self.assertEqual(provider['baseUrl'], 'https://litellm.vanillax.me/v1')
        # /login cannot configure a custom provider, so the key is supplied
        # here; it must stay an indirection, never a literal secret.
        self.assertRegex(provider['apiKey'], r'^[$!]')
        model = provider['models'][0]
        config = read('my-apps/ai/litellm/config.yaml')
        route = next(m for m in config['model_list'] if m['model_name'] == model['id'])
        self.assertEqual(route['litellm_params']['api_base'], 'http://vllm-service.vllm.svc.cluster.local:8080/v1')
        self.assertGreaterEqual(route['litellm_params']['timeout'], 1800)
        self.assertEqual(model['contextWindow'], 262144)
        env = (ROOT / 'my-apps/ai/open-webui/open-webui-configmap.env').read_text()
        for name in ['OPENAI_API_BASE_URL', 'OPENAI_API_BASE_URLS']:
            self.assertIn(name + '=http://litellm-service.litellm.svc.cluster.local:4000/v1', env)


class AllLLMClientsTests(unittest.TestCase):
    APPS = [
        'my-apps/ai/open-webui', 'my-apps/ai/hindsight', 'my-apps/ai/surfsense',
        'my-apps/ai/perplexica', 'my-apps/ai/presenton', 'my-apps/ai/comfyui',
        'my-apps/home/n8n', 'my-apps/home/project-nomad',
        'my-apps/media/karakeep', 'my-apps/media/worldmonitor',
        'my-apps/utility/deal-scout', 'my-apps/development/news-reader',
        'monitoring/holmesgpt', 'monitoring/keep',
    ]

    def test_no_declared_client_bypasses_gateway_including_tracked_env_files(self):
        subprocess.run(['python3', str(ROOT / 'scripts/validate-llm-gateway.py')], check=True)

    def test_deal_scout_authenticates_without_a_source_overlay(self):
        # Auth used to be an init container that rewrote app.py against a pinned
        # source hash. The image reads the key itself since v0.13.0; reinstating
        # the overlay would fail that hash check and never start the pod.
        pod = read('my-apps/utility/deal-scout/deployment.yaml')['spec']['template']['spec']
        app = next(c for c in pod['containers'] if c['name'] == 'deal-scout')
        self.assertEqual(pod.get('initContainers', []), [])
        self.assertFalse(any(m['mountPath'].startswith('/app') for m in app['volumeMounts']))
        key = next(e for e in app['env'] if e['name'] == 'LITELLM_API_KEY')
        self.assertEqual(key['valueFrom']['secretKeyRef']['key'], 'LITELLM_API_KEY')

    def test_every_client_renders_a_consumed_gateway_credential(self):
        for app in self.APPS:
            with self.subTest(app=app):
                rendered = subprocess.check_output(
                    ['kustomize', 'build', str(ROOT / app), '--enable-helm'], text=True)
                documents = [d for d in yaml.safe_load_all(rendered) if d]
                credentials = []
                for document in documents:
                    if document['kind'] != 'ExternalSecret':
                        continue
                    if any(entry.get('remoteRef', {}).get('key') == 'litellm' and
                           entry['remoteRef'].get('property') == 'master_key'
                           for entry in document['spec'].get('data', [])):
                        target = document['spec'].get('target', {}).get('name', document['metadata']['name'])
                        for entry in document['spec']['data']:
                            if entry.get('remoteRef', {}).get('key') == 'litellm':
                                credentials.append((target, entry['secretKey']))
                self.assertTrue(credentials, 'App has no ExternalSecret for the gateway key')
                consumers = [d for d in documents if d['kind'] in
                             ['Deployment', 'StatefulSet', 'Job', 'WorkerDeployment']]

                def objects(value):
                    if isinstance(value, dict):
                        yield value
                        for child in value.values():
                            yield from objects(child)
                    elif isinstance(value, list):
                        for child in value:
                            yield from objects(child)

                nodes = list(objects(consumers))
                for name, key in credentials:
                    used = any(node.get('secretKeyRef', {}).get('name') == name and
                               node['secretKeyRef'].get('key') == key for node in nodes)
                    imported = any(node.get('secretRef', {}).get('name') == name for node in nodes)
                    projected = any(node.get('secret', {}).get('secretName') == name for node in nodes)
                    self.assertTrue(used or imported or projected,
                                    f'Gateway credential {name}/{key} is not consumed')
                self.assertIn('litellm-service.litellm.svc.cluster.local:4000', rendered)


class LangfuseCredentialBootstrapTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'scripts/bootstrap-langfuse-secrets.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_existing_credentials_are_never_rotated(self):
        item = {'fields': [{'label': name, 'value': 'retained'} for name in self.module.REQUIRED]}
        with patch.object(self.module, 'op', side_effect=[[{'id': 'existing', 'title': 'langfuse'}], item]) as op:
            with contextlib.redirect_stdout(io.StringIO()):
                self.module.main()
        self.assertEqual(op.call_count, 2)
        self.assertFalse(any('create' in call.args for call in op.call_args_list))

    def test_missing_existing_fields_fail_without_replacement(self):
        with patch.object(self.module, 'op', side_effect=[[{'id': 'existing', 'title': 'langfuse'}], {'fields': []}]) as op:
            with self.assertRaisesRegex(SystemExit, 'Existing item preserved'):
                self.module.main()
        self.assertEqual(op.call_count, 2)

    def test_duplicate_item_titles_are_rejected(self):
        with patch.object(self.module, 'op', return_value=[{'title': 'langfuse'}, {'title': 'langfuse'}]) as op:
            with self.assertRaisesRegex(SystemExit, 'Multiple langfuse items'):
                self.module.main()
        self.assertEqual(op.call_count, 1)

    def test_generated_credentials_use_stdin_and_do_not_appear_in_output(self):
        output = io.StringIO()
        with patch.object(self.module, 'op', side_effect=[[], {'email': 'test@example.invalid'}, {'id': 'created'}]) as op:
            with contextlib.redirect_stdout(output):
                self.module.main()
        fields = {f['label']: f['value'] for f in op.call_args.kwargs['payload']['fields']}
        self.assertEqual(set(fields), self.module.REQUIRED)
        self.assertRegex(fields['encryption-key'], r'^[0-9a-f]{64}$')
        self.assertRegex(fields['redis-password'], r'^[0-9a-f]{64}$')
        for value in fields.values():
            self.assertNotIn(value, output.getvalue())
        self.assertEqual(op.call_args.args, ('item', 'create', '--vault', 'homelab-prod'))


if __name__ == '__main__':
    unittest.main()
