"""Exercise rendered delivery boundaries without contacting Kubernetes."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('practice', ROOT / 'scripts/platform-practice.py')
practice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(practice)


def render(stage):
    return [d for d in yaml.safe_load_all(subprocess.check_output(
        ['kustomize', 'build', str(ROOT / 'my-apps/practice' / ('radar-practice-' + stage))], text=True)) if d]


class DeliveryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stages = {stage: render(stage) for stage in ['int', 'cert', 'prod']}

    def test_distinct_stages_and_no_production_state_or_credentials(self):
        for stage, docs in self.stages.items():
            for obj in docs:
                self.assertNotIn(obj['kind'], ['Secret', 'ExternalSecret', 'PersistentVolumeClaim', 'TemporalWorkerDeployment'])
                if obj['kind'] != 'Namespace':
                    self.assertEqual(obj['metadata']['namespace'], 'radar-practice-' + stage)
                if obj['kind'] == 'Deployment':
                    pod = obj['spec']['template']['spec']
                    self.assertFalse(pod['automountServiceAccountToken'])
                    self.assertFalse(any('persistentVolumeClaim' in v for v in pod['volumes']))
                    env = {e['name']: e.get('value') for e in pod['containers'][0]['env']}
                    self.assertEqual(env['DISABLE_WORKFLOW_ROUTES'], '1')
                    self.assertEqual(env['TEMPORAL_ADDRESS'], '127.0.0.1:1')
                    self.assertRegex(pod['containers'][0]['image'], r'@sha256:[a-f0-9]{64}$')

    def test_services_and_spread_select_only_their_own_release(self):
        docs = self.stages['prod']
        deployments = [d for d in docs if d['kind'] == 'Deployment']
        for service in (d for d in docs if d['kind'] == 'Service'):
            selector = service['spec']['selector']
            matched = [d for d in deployments if all(d['spec']['template']['metadata']['labels'].get(k) == v for k, v in selector.items())]
            self.assertEqual(len(matched), 1, service['metadata']['name'])
            d = matched[0]
            self.assertEqual(d['metadata']['name'], service['metadata']['name'])
            pod = d['spec']['template']['spec']
            self.assertEqual(pod['topologySpreadConstraints'][0]['labelSelector']['matchLabels'], selector)
            self.assertEqual(pod['topologySpreadConstraints'][0]['topologyKey'], 'topology.kubernetes.io/zone')
            self.assertEqual(pod['topologySpreadConstraints'][0]['nodeTaintsPolicy'], 'Honor')
            self.assertNotIn('replicas', d['spec'])

    def test_split_and_preview_target_existing_independent_services(self):
        docs = self.stages['prod']
        routes = {d['metadata']['name']: d for d in docs if d['kind'] == 'HTTPRoute'}
        refs = routes['radar-practice']['spec']['rules'][0]['backendRefs']
        self.assertEqual({r['name']: r['weight'] for r in refs}, {'radar-api': 99, 'radar-api-canary': 1})
        self.assertEqual(routes['radar-preview']['spec']['rules'][0]['backendRefs'][0]['name'], 'radar-api-canary')
        for r in routes.values():
            self.assertEqual(r['metadata']['labels']['delivery.vanillax.dev/weights'], 'git')
            self.assertEqual(r['spec']['parentRefs'][0]['name'], 'gateway-internal-technitium')
            self.assertNotIn('external-dns', r['metadata']['labels'])

    def test_cpu_hpa_and_memory_vpa_have_separate_ownership(self):
        docs = self.stages['prod']
        vpas = {d['spec']['targetRef']['name']: d for d in docs if d['kind'] == 'VerticalPodAutoscaler'}
        for hpa in (d for d in docs if d['kind'] == 'HorizontalPodAutoscaler'):
            name = hpa['spec']['scaleTargetRef']['name']
            self.assertEqual(vpas[name]['spec']['resourcePolicy']['containerPolicies'][0]['controlledResources'], ['memory'])
            self.assertLessEqual(hpa['spec']['maxReplicas'], 3)
        appset = yaml.safe_load((ROOT / 'infrastructure/controllers/argocd/apps/appsets/my-apps-appset.yaml').read_text())
        self.assertIn('"practice"', appset['spec']['templatePatch'])
        self.assertIn('/spec/replicas', appset['spec']['templatePatch'])

    def test_first_install_does_not_wait_on_autoscalers_before_their_targets(self):
        def wave(d):
            return int(d['metadata'].get('annotations', {}).get('argocd.argoproj.io/sync-wave', '0'))
        for docs in self.stages.values():
            targets = {d['metadata']['name']: d for d in docs if d['kind'] == 'Deployment'}
            instrumentation = next(d for d in docs if d['kind'] == 'Instrumentation')
            for target in targets.values():
                self.assertLess(wave(instrumentation), wave(target))
            for d in docs:
                if d['kind'] not in ['HorizontalPodAutoscaler', 'VerticalPodAutoscaler']:
                    continue
                ref = d['spec'].get('scaleTargetRef', d['spec'].get('targetRef'))
                self.assertGreaterEqual(wave(d), wave(targets[ref['name']]))

    def test_git_weights_survive_the_actual_argo_ignore_expression(self):
        values = yaml.safe_load((ROOT / 'infrastructure/controllers/argocd/values.yaml').read_text())
        key = 'resource.customizations.ignoreDifferences.gateway.networking.k8s.io_HTTPRoute'
        rules = yaml.safe_load(values['configs']['cm'][key])['jqPathExpressions']
        expression = ' | '.join('del(' + rule + ')' for rule in rules)
        route = copy.deepcopy(next(d for d in self.stages['prod'] if d['kind'] == 'HTTPRoute' and d['metadata']['name'] == 'radar-practice'))
        cleaned = json.loads(subprocess.check_output(['jq', expression], input=json.dumps(route), text=True))
        self.assertEqual(cleaned['spec']['rules'][0]['backendRefs'][0]['weight'], 99)
        route['metadata']['labels'].pop('delivery.vanillax.dev/weights')
        cleaned = json.loads(subprocess.check_output(['jq', expression], input=json.dumps(route), text=True))
        self.assertNotIn('weight', cleaned['spec']['rules'][0]['backendRefs'][0])

    def test_gateway_pdb_spread_and_sdk_identity_preservation(self):
        d = yaml.safe_load((ROOT / 'infrastructure/controllers/opentelemetry-operator/collector-gateway.yaml').read_text())['spec']
        self.assertEqual(d['replicas'], 2)
        self.assertEqual(d['podDisruptionBudget']['maxUnavailable'], 1)
        spread = d['topologySpreadConstraints'][0]
        self.assertEqual(spread['labelSelector']['matchLabels']['app.kubernetes.io/name'], 'otel-gateway-collector')
        self.assertEqual(spread['whenUnsatisfiable'], 'DoNotSchedule')
        attrs = d['config']['processors']['resource']['attributes']
        self.assertTrue(all(a['action'] == 'insert' for a in attrs if a['key'] == 'service.name'))

    def test_shared_changes_are_in_argo_cache_hints(self):
        docs = list(yaml.safe_load_all(subprocess.check_output(['kustomize','build',str(ROOT/'infrastructure/controllers/argocd/apps')],text=True)))
        appset = next(d for d in docs if d and d.get('kind')=='ApplicationSet' and d['metadata']['name']=='my-apps')
        self.assertIn('/my-apps/common',appset['spec']['template']['metadata']['annotations']['argocd.argoproj.io/manifest-generate-paths'])

    def test_promotion_changes_one_stage_and_preserves_digest(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'practice'
            shutil.copytree(ROOT/'my-apps/practice',target)
            with patch.object(practice,'STAGES',target):
                initial = {stage: practice.get_release(stage) for stage in ['int','cert','candidate','prod']}
                practice.set_release('cert','v1.2.3','sha256:'+'a'*64)
                self.assertEqual(practice.get_release('cert'),('v1.2.3','sha256:'+'a'*64))
                for stage in ['int','candidate','prod']:self.assertEqual(practice.get_release(stage),initial[stage])
                practice.set_weight(10)
                route=practice.read(target/'radar-practice-prod/httproute.yaml')
                self.assertEqual([r['weight'] for r in route['spec']['rules'][0]['backendRefs']],[90,10])
                with self.assertRaises(ValueError):practice.set_weight(101)

    def test_promoted_pin_and_version_reach_only_the_target_pods(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            apps = Path(directory) / 'my-apps'
            shutil.copytree(ROOT / 'my-apps/practice', apps / 'practice')
            shutil.copytree(ROOT / 'my-apps/common/radar-practice', apps / 'common/radar-practice')
            with patch.object(practice, 'STAGES', apps / 'practice'):
                for slot, tag in [('int', 'v2.0.0'), ('cert', 'v3.0.0'), ('candidate', 'v4.0.0'), ('prod', 'v5.0.0')]:
                    practice.set_release(slot, tag, 'sha256:' + 'a' * 64)
                expected = {('int', 'v1'): 'v2.0.0', ('cert', 'v1'): 'v3.0.0',
                            ('prod', 'v2'): 'v4.0.0', ('prod', 'v1'): 'v5.0.0'}
                for stage in ['int', 'cert', 'prod']:
                    docs = yaml.safe_load_all(subprocess.check_output(
                        ['kustomize', 'build', str(apps / 'practice' / ('radar-practice-' + stage))], text=True))
                    for d in docs:
                        if d['kind'] != 'Deployment':
                            continue
                        pod = d['spec']['template']
                        slot = pod['metadata']['labels']['delivery.vanillax.dev/slot']
                        version = expected[stage, slot]
                        self.assertEqual(pod['metadata']['labels']['app.kubernetes.io/version'], version)
                        self.assertEqual(d['metadata']['labels']['app.kubernetes.io/version'], version)
                        self.assertEqual(pod['spec']['containers'][0]['image'],
                                         practice.IMAGE + ':' + version + '@sha256:' + 'a' * 64)

    def test_registry_republication_is_rejected(self):
        with patch.object(subprocess,'check_output',return_value=json.dumps('sha256:'+'b'*64)):
            with self.assertRaisesRegex(ValueError,'republished'):
                practice.verify_release('v1.1.17','sha256:'+'a'*64)


if __name__ == '__main__':
    unittest.main()
