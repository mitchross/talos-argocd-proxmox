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
        providers = next(b['providers'] for b in blocks if 'providers' in b)
        provider = providers['vanillax-vllm']
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

        openrouter_provider = providers['vanillax-openrouter']
        self.assertEqual(openrouter_provider['baseUrl'], provider['baseUrl'])
        self.assertRegex(openrouter_provider['apiKey'], r'^[$!]')
        self.assertEqual(openrouter_provider['compat']['thinkingFormat'], 'openrouter')
        self.assertTrue(openrouter_provider['compat']['requiresReasoningContentOnAssistantMessages'])
        deepseek = openrouter_provider['models'][0]
        deepseek_route = next(m for m in config['model_list'] if m['model_name'] == deepseek['id'])
        self.assertEqual(deepseek_route['litellm_params']['model'],
                         'openrouter/~deepseek/deepseek-flash-latest')
        self.assertGreaterEqual(deepseek_route['litellm_params']['timeout'], 1800)
        self.assertEqual(deepseek['contextWindow'], 1_048_576)
        self.assertEqual(deepseek['maxTokens'], 32_768)
        self.assertEqual(deepseek['thinkingLevelMap'], {
            'off': None, 'minimal': None, 'low': 'low', 'medium': None,
            'high': 'high', 'xhigh': None, 'max': 'max',
        })
        self.assertEqual(deepseek['cost'], {'input': 0.3, 'output': 1.2,
                                            'cacheRead': 0.03, 'cacheWrite': 0})
        auto_provider = providers['vanillax-auto']
        self.assertEqual(auto_provider['baseUrl'], provider['baseUrl'])
        self.assertRegex(auto_provider['apiKey'], r'^[$!]')
        self.assertFalse(auto_provider['compat']['supportsReasoningEffort'])
        self.assertTrue(auto_provider['compat']['requiresReasoningContentOnAssistantMessages'])
        auto_model = auto_provider['models'][0]
        self.assertEqual(auto_model['id'], 'pi-auto')
        self.assertEqual(auto_model['contextWindow'], 262144)
        self.assertEqual(auto_model['maxTokens'], 32768)
        self.assertEqual(auto_model['cost'], deepseek['cost'])
        self.assertIn('CachyOS workstation inventory', guide)
        self.assertIn('@narumitw/pi-subagents` 3.0.1', guide)
        self.assertIn('diff -u ~/.pi/agent/extensions/qwen-sampling.ts', guide)
        self.assertIn('pi-withflash', guide)
        self.assertIn('pi-flash', guide)
        self.assertIn('--models $AUTO', guide)

        fields = {x['secretKey']: x['remoteRef'] for x in
                  read('my-apps/ai/litellm/externalsecret.yaml')['spec']['data']}
        self.assertEqual(fields['OPENROUTER_API_KEY'], {
            'key': 'open-router', 'property': 'api-key-open-router'})
        self.assertNotIn('MOONSHOT_API_KEY', fields)
        deployment = container(read('my-apps/ai/litellm/deployment.yaml'))
        upstream = next(e for e in deployment['env'] if e['name'] == 'OPENROUTER_API_KEY')
        self.assertEqual(upstream['valueFrom']['secretKeyRef'], {
            'name': 'litellm-secrets', 'key': 'OPENROUTER_API_KEY'})

        env = (ROOT / 'my-apps/ai/open-webui/open-webui-configmap.env').read_text()
        for name in ['OPENAI_API_BASE_URL', 'OPENAI_API_BASE_URLS']:
            self.assertIn(name + '=http://litellm-service.litellm.svc.cluster.local:4000/v1', env)

    def test_pi_auto_router_keeps_easy_work_local_and_escalates_hard_work(self):
        config = read('my-apps/ai/litellm/config.yaml')
        routes = {route['model_name']: route for route in config['model_list']}
        auto = routes['pi-auto']
        params = auto['litellm_params']
        self.assertEqual(params['model'], 'auto_router/complexity_router')
        self.assertTrue(params['drop_params'])
        router = params['complexity_router_config']
        self.assertEqual(router['classifier_type'], 'llm')
        self.assertEqual(router['classifier_fallback'], 'default_model')
        self.assertTrue(router['classifier_context_include_assistant_turns'])
        self.assertGreater(router['classifier_context_window_size'], 0)
        classifier = routes[router['classifier_llm_config']['model']]['litellm_params']
        # Classification must stay local, avoid recursive routing, and produce JSON without thinking.
        self.assertEqual(classifier['model'], routes['qwen3.8-27b']['litellm_params']['model'])
        self.assertEqual(classifier['api_base'], routes['qwen3.8-27b']['litellm_params']['api_base'])
        self.assertEqual(classifier['extra_body']['chat_template_kwargs'], {
            'enable_thinking': False, 'preserve_thinking': False,
        })
        self.assertLessEqual(classifier['max_tokens'], 128)
        # Sampled classification routed one ask three different ways across runs.
        self.assertEqual(classifier['temperature'], 0)
        self.assertEqual(classifier['top_p'], 1)
        for noisy in ('presence_penalty', 'frequency_penalty'):
            self.assertNotIn(noisy, classifier)
        self.assertNotIn('top_k', classifier['extra_body'])
        self.assertEqual(router['tiers'], {
            'SIMPLE': 'qwen3.8-27b',
            'MEDIUM': 'qwen3.8-27b',
            'COMPLEX': 'deepseek-flash',
            'REASONING': 'deepseek-flash',
        })
        # Paid tiers must never fall back to the provider's default effort.
        efforts = {
            tier: entries[0]['litellm_params']['reasoning_effort']
            for tier, entries in router['tier_model_configs'].items()
        }
        self.assertEqual(efforts, {'COMPLEX': 'high', 'REASONING': 'max'})
        # Local work is the point of the two 3090s: Qwen must keep a real tier.
        self.assertEqual(router['tiers']['MEDIUM'], 'qwen3.8-27b')
        for tier, entries in router['tier_model_configs'].items():
            self.assertEqual(entries[0]['model_name'], router['tiers'][tier])
            # OpenRouter exposes low/high/max for Flash; drop_params eats anything else.
            self.assertIn(entries[0]['litellm_params']['reasoning_effort'],
                          {'low', 'high', 'max'})
        # LiteLLM rejects stall escalation unless every request is classified.
        self.assertTrue(router['stall_escalation_enabled'])
        self.assertEqual(router['classification_mode'], 'every_request')
        self.assertFalse(router['session_affinity'])
        self.assertLessEqual(router['stall_escalation_repeat_threshold'],
                             router['stall_escalation_window'])
        self.assertTrue(router['enable_context_window_escalation'])
        self.assertFalse(router['return_raw_model_name'])
        # v1.102.0 flips this default and would hand Flash a 943K output cap.
        self.assertFalse(router['max_tokens_from_tier_model'])
        # An unclassifiable turn resolves upward; guessing cheap is the costly miss.
        self.assertEqual(params['complexity_router_default_model'], 'deepseek-flash')
        # vLLM being down must not fail the request.
        settings = config['router_settings']
        self.assertEqual(settings['fallbacks'], [{'qwen3.8-27b': ['deepseek-flash']}])
        self.assertEqual(settings['context_window_fallbacks'],
                         [{'qwen3.8-27b': ['deepseek-flash']}])
        self.assertEqual(auto['model_info'], {
            'max_input_tokens': 229376,
            'max_output_tokens': 32768,
        })
        self.assertEqual(routes['qwen3.8-27b']['litellm_params']['api_base'],
                         'http://vllm-service.vllm.svc.cluster.local:8080/v1')
        deepseek = routes['deepseek-flash']
        self.assertEqual(deepseek['litellm_params']['model'],
                         'openrouter/~deepseek/deepseek-flash-latest')
        self.assertEqual(deepseek['model_info'], {
            'input_cost_per_token': 0.0000003,
            'output_cost_per_token': 0.0000012,
            'cache_read_input_token_cost': 0.00000003,
            'max_input_tokens': 1048576,
            'max_output_tokens': 943718,
        })
        image = container(read('my-apps/ai/litellm/deployment.yaml'))['image']
        self.assertEqual(image, 'ghcr.io/berriai/litellm:v1.101.0')

        guide = (ROOT / 'docs/domains/ai-gpu/pi-agent-local-dev.md').read_text()
        self.assertIn('SIMPLE` / `MEDIUM` work on local Qwen', guide)
        self.assertIn('COMPLEX` / `REASONING`', guide)
        self.assertIn('stall_escalation_enabled', guide)
        self.assertIn('LITELLM ESCALATE', guide)
        self.assertIn('classification_mode: every_request', guide)
        self.assertIn('beta', guide.lower())


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
