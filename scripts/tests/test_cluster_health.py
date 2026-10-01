"""Offline smoke regression tests using a fake kubectl; no cluster access."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'validate-cluster-health.sh'


class HealthTests(unittest.TestCase):
    def run_check(self, case):
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / 'kubectl'
            stub.write_text('''#!/usr/bin/env python3
import json, os, sys
resource = sys.argv[2]
case = os.environ['HEALTH_CASE']
if case == 'all-fail' or case == 'fail-' + resource:
    print('API unreachable', file=sys.stderr); sys.exit(1)
if case == 'invalid-' + resource:
    print('not json'); sys.exit(0)
if case == 'empty-' + resource:
    print('{"items": []}'); sys.exit(0)
objects = {
 'nodes': {'metadata': {'name': 'worker'}, 'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}},
 'pods': {'metadata': {'name': 'pod', 'namespace': 'app'}, 'status': {'phase': 'Running'}},
 'applications.argoproj.io': {'metadata': {'name': 'root'}, 'status': {'sync': {'status': 'Synced'}, 'health': {'status': 'Healthy'}}},
 'volumes.longhorn.io': {'metadata': {'name': 'volume'}, 'status': {'robustness': 'healthy'}}}
obj = objects[resource]
if case == 'not-ready': objects['nodes']['status']['conditions'][0]['status'] = 'False'
if case == 'bad-pod': objects['pods']['status']['phase'] = 'Pending'
if case == 'missing-argo-status': objects['applications.argoproj.io']['status'] = {}
if case == 'failed-argo-operation': objects['applications.argoproj.io']['status']['operationState'] = {'phase': 'Failed'}
if case == 'degraded-volume': objects['volumes.longhorn.io']['status']['robustness'] = 'degraded'
print(json.dumps({'items': [obj]}))
''')
            stub.chmod(0o755)
            return subprocess.run(['bash', str(SCRIPT), '--summary-only'], capture_output=True,
                                  text=True, env={**os.environ, 'PATH': tmp + ':' + os.environ['PATH'],
                                                  'HEALTH_CASE': case})

    def test_healthy(self):
        result = self.run_check('healthy')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('RESULT: HEALTHY', result.stdout)
        self.assertNotIn('Safe to proceed', result.stdout)
        self.assertIn('does not authorize destructive', result.stdout)

    def test_query_failure_and_invalid_output(self):
        for resource in ['nodes', 'pods', 'applications.argoproj.io', 'volumes.longhorn.io']:
            for prefix in ['fail-', 'invalid-', 'empty-']:
                with self.subTest(case=prefix + resource):
                    result = self.run_check(prefix + resource)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertIn('RESULT: UNKNOWN', result.stdout)
                    self.assertNotIn('all Ready', result.stdout)
        result = self.run_check('all-fail')
        self.assertEqual(2, result.returncode)
        self.assertNotIn('HEALTHY:', result.stdout)

    def test_observed_issues(self):
        for case in ['not-ready', 'bad-pod', 'missing-argo-status',
                     'failed-argo-operation', 'degraded-volume']:
            with self.subTest(case=case):
                result = self.run_check(case)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn('RESULT: UNHEALTHY', result.stdout)


if __name__ == '__main__':
    unittest.main()
