"""Offline live-gate tests; fixtures never connect to production."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('live_gate', Path(__file__).parents[1] / 'gitops-live-gate.py')
live = importlib.util.module_from_spec(spec); spec.loader.exec_module(live)
COMMIT = 'a' * 40
OLD = 'b' * 40


class LiveGateTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'context': 'fixture', 'server': 'https://fixture.invalid',
            'application_sets': [{'name': 'infrastructure', 'fields': {
                '/spec/syncPolicy/preserveResourcesOnDeletion': True,
                '/spec/generators/0/git/directories': [{'path': 'infrastructure/platform/container-registry'}]}}],
            'applications': [{'name': 'infrastructure-container-registry', 'owner_appset': 'infrastructure',
                'resources_finalizer': 'absent', 'fields': {
                    '/spec/source/path': 'infrastructure/platform/container-registry',
                    '/spec/destination/namespace': 'container-registry'}}],
            'resources': [{'kind': 'PersistentVolumeClaim', 'name': 'registry-data', 'namespace': 'container-registry',
                'uid': 'original-pvc', 'fields': {'/spec/volumeName': 'original-pv', '/spec/storageClassName': 'longhorn'}}]}
        status = {'sync': {'status': 'Synced', 'revision': COMMIT}, 'health': {'status': 'Healthy'},
                  'operationState': {'phase': 'Succeeded', 'syncResult': {'revision': COMMIT}, 'finishedAt': '2026-09-28T14:30:11Z'}}
        root = {'metadata': {'name': 'root'}, 'spec': {'source': {'repoURL': live.REPO, 'path': live.ROOT_PATH, 'targetRevision': 'main'}}, 'status': copy.deepcopy(status)}
        appset = {'metadata': {'name': 'infrastructure', 'uid': 'appset-uid'}, 'spec': {
            'syncPolicy': {'preserveResourcesOnDeletion': True},
            'generators': [{'git': {'directories': [{'path': 'infrastructure/platform/container-registry'}]}}]}}
        app = {'metadata': {'name': 'infrastructure-container-registry', 'ownerReferences': [
            {'name': 'infrastructure', 'kind': 'ApplicationSet', 'uid': 'appset-uid', 'controller': True}]},
            'spec': {'source': {'repoURL': live.REPO, 'path': 'infrastructure/platform/container-registry', 'targetRevision': 'main'},
                     'destination': {'namespace': 'container-registry'}}, 'status': copy.deepcopy(status)}
        pvc = {'metadata': {'name': 'registry-data', 'uid': 'original-pvc'}, 'spec': {'volumeName': 'original-pv', 'storageClassName': 'longhorn'}, 'status': {'phase': 'Bound'}}
        self.objects = {'root': root, 'infrastructure': appset, 'infrastructure-container-registry': app, 'registry-data': pvc}

    def check(self):
        gate = live.Gate(lambda kind, name, namespace: self.objects[name], lambda sha: sha == COMMIT, COMMIT)
        passed = gate.inspect(self.plan)
        return passed, gate

    def test_exact_prerequisite_fields_and_surviving_resources_pass(self):
        passed, gate = self.check()
        self.assertTrue(passed, gate.findings)
        self.assertTrue(any(o['check'] == 'surviving UID' for o in gate.observations))

    def test_healthy_synced_does_not_prove_operation_revision(self):
        self.objects['root']['status']['operationState']['syncResult']['revision'] = OLD
        passed, gate = self.check()
        self.assertFalse(passed)
        self.assertTrue(any(f['check'] == 'successful operation revision' for f in gate.findings))

    def test_merged_but_safety_change_not_live_blocks(self):
        self.objects['infrastructure']['spec']['syncPolicy']['preserveResourcesOnDeletion'] = False
        self.objects['infrastructure-container-registry']['metadata']['finalizers'] = ['resources-finalizer.argocd.argoproj.io']
        passed, gate = self.check()
        self.assertFalse(passed)
        self.assertTrue(any(f['check'] == '/spec/syncPolicy/preserveResourcesOnDeletion' for f in gate.findings))
        self.assertTrue(any(f['check'] == 'resources finalizer' for f in gate.findings))

    def test_wrong_generator_owner_uid_and_recreated_pvc(self):
        self.objects['infrastructure']['spec']['generators'][0]['git']['directories'][0]['path'] = 'infrastructure/controllers/container-registry'
        self.objects['infrastructure-container-registry']['metadata']['ownerReferences'][0]['uid'] = 'stale-controller'
        self.objects['registry-data']['metadata']['uid'] = 'recreated-pvc'
        self.objects['registry-data']['spec']['volumeName'] = 'recreated-pv'
        passed, gate = self.check()
        self.assertFalse(passed)
        for check in ['/spec/generators/0/git/directories', 'controller ownership', 'surviving UID', '/spec/volumeName']:
            self.assertTrue(any(f['check'] == check for f in gate.findings), check)

    def test_failed_root_and_terminating_persistent_resource(self):
        self.objects['root']['status']['operationState']['phase'] = 'Failed'
        self.objects['registry-data']['metadata']['deletionTimestamp'] = '2026-09-28T14:12:00Z'
        self.assertFalse(self.check()[0])

    def test_unavailable_observation_never_passes(self):
        gate = live.Gate(lambda *args: (_ for _ in ()).throw(ValueError('unreachable')), lambda sha: True, COMMIT)
        with self.assertRaisesRegex(ValueError, 'unreachable'):
            gate.inspect(self.plan)

    def test_plan_requires_persistent_uid_binding_and_explicit_scope(self):
        for missing in ['context', 'application_sets', 'applications', 'resources']:
            plan = copy.deepcopy(self.plan); del plan[missing]
            with self.assertRaises(ValueError): live.validate_plan(plan)
        del self.plan['resources'][0]['uid']
        with self.assertRaises(ValueError): live.validate_plan(self.plan)

    def cli(self, commands, failure=None, descendant=False):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / 'plan.json'; plan.write_text(json.dumps(self.plan))
            def fake(*args):
                commands.append(args)
                if args[0] == 'git':
                    if failure == 'unmerged' and 'merge-base' in args: raise ValueError('commit not on main')
                    return ''
                if 'config' in args: return 'https://wrong.invalid' if failure == 'cluster' else self.plan['server']
                if 'get' in args: return json.dumps(self.objects[args[args.index('get') + 2]])
                if args[0] == 'gh': return json.dumps({'state': 'OPEN' if failure == 'pr' else 'MERGED', 'baseRefName': 'main', 'mergeCommit': {'oid': COMMIT}})
                raise AssertionError(args)
            output = io.StringIO()
            with patch.object(sys, 'argv', ['gate', '--plan', str(plan), '--commit', COMMIT, '--pr', '2617', '--format', 'json'] + (['--allow-descendant'] if descendant else [])), patch.object(live, 'command', fake), patch('sys.stdout', output):
                code = live.main()
            return code, json.loads(output.getvalue())

    def test_cli_read_only_queries_and_json_report(self):
        commands = []; code, report = self.cli(commands)
        self.assertEqual(0, code)
        self.assertEqual('PASS', report['status'])
        self.assertEqual(2617, report['merged_pr'])
        self.assertIn('valid_until', report)
        kubectl = [args for args in commands if args[0] == 'kubectl']
        self.assertTrue(kubectl)
        self.assertTrue(all('get' in args or 'config' in args for args in kubectl))
        self.assertTrue(all('--context' in args for args in kubectl))

    def test_cli_unmerged_commit_pr_and_wrong_cluster_block(self):
        for case in ('unmerged', 'pr', 'cluster'):
            with self.subTest(case=case):
                commands = []; code, report = self.cli(commands, failure=case)
                self.assertEqual(1, code)
                self.assertEqual('BLOCK', report['status'])
                self.assertFalse(any('get' in args for args in commands if args[0] == 'kubectl'))

    def test_cli_newer_merged_operation_requires_explicit_descendant_mode(self):
        self.objects['root']['status']['sync']['revision'] = OLD
        self.objects['root']['status']['operationState']['syncResult']['revision'] = OLD
        self.assertEqual(1, self.cli([])[0])
        self.assertEqual(0, self.cli([], descendant=True)[0])

    def test_cli_failed_revision_is_nonzero(self):
        self.objects['root']['status']['operationState']['syncResult']['revision'] = OLD
        code, report = self.cli([])
        self.assertEqual(1, code)
        self.assertEqual('BLOCK', report['status'])


if __name__ == '__main__':
    unittest.main()
