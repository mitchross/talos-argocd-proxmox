"""Check the wiring that previously allowed healthy pods with missing telemetry."""
import json
from pathlib import Path
import re
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return yaml.safe_load((ROOT / path).read_text())


def container(document):
    return document['spec']['template']['spec']['containers'][0]


def environment(document):
    return {entry['name']: entry.get('value') for entry in container(document)['env']}


class AIObservabilityTests(unittest.TestCase):
    def test_ai_capture_topics_have_a_supported_consumer_and_bootstrap(self):
        app = 'my-apps/development/posthog/'
        consumer = read(app + 'core/ingestion-ai.yaml')
        config = environment(consumer)
        # Combined mode hardcodes its subscriptions and ignores the topic override.
        self.assertEqual(config['PLUGIN_SERVER_MODE'], 'ingestion-v2')
        topic = config['INGESTION_CONSUMER_CONSUME_TOPIC']
        self.assertEqual(config['INGESTION_CONSUMER_GROUP_ID'], 'clickhouse-ingestion-ai')
        # Dedicated-table reads are disabled in the live self-hosted UI.
        self.assertEqual(config['INGESTION_AI_EVENT_SPLITTING_ENABLED'], 'false')
        for filename in ['capture.yaml', 'capture-ai.yaml']:
            capture = next(yaml.safe_load_all((ROOT / app / 'core' / filename).read_text()))
            self.assertEqual(environment(capture)['CAPTURE_ANALYTICS_AI_EVENTS_TOPIC'], topic)
        bootstrap = (ROOT / app / 'scripts/init-kafka.sh').read_text()
        topics = re.search(r'for topic in (.*); do', bootstrap).group(1).split()
        self.assertIn(topic, topics)
        self.assertIn('clickhouse_ai_events_json', topics)
        self.assertEqual(container(consumer)['image'], container(read(app + 'core/ingestion.yaml'))['image'])
        self.assertIn('core/ingestion-ai.yaml', read(app + 'kustomization.yaml')['resources'])

    def test_metrics_auth_and_webui_use_the_actual_gateway_secret_source(self):
        app = 'my-apps/ai/litellm/'
        config = read(app + 'config.yaml')['litellm_settings']
        self.assertIn('prometheus', config['callbacks'])
        self.assertTrue(config['require_auth_for_metrics_endpoint'])
        self.assertEqual(sorted(set(config['prometheus_latency_buckets'])), config['prometheus_latency_buckets'])
        self.assertGreaterEqual(max(config['prometheus_latency_buckets']), 1800)
        self.assertIn('posthog', config['success_callback'])
        self.assertIn('posthog', config['failure_callback'])
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
        self.assertNotIn('apiKey', provider)
        model = provider['models'][0]
        config = read('my-apps/ai/litellm/config.yaml')
        route = next(m for m in config['model_list'] if m['model_name'] == model['id'])
        self.assertEqual(route['litellm_params']['api_base'], 'http://vllm-service.vllm.svc.cluster.local:8080/v1')
        self.assertGreaterEqual(route['litellm_params']['timeout'], 1800)
        self.assertEqual(model['contextWindow'], 262144)
        env = (ROOT / 'my-apps/ai/open-webui/open-webui-configmap.env').read_text()
        for name in ['OPENAI_API_BASE_URL', 'OPENAI_API_BASE_URLS']:
            self.assertIn(name + '=http://litellm-service.litellm.svc.cluster.local:4000/v1', env)


if __name__ == '__main__':
    unittest.main()
