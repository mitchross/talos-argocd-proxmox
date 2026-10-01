"""Reduced real-layout fixtures for September discovery races and data transitions."""
import copy
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

spec = importlib.util.spec_from_file_location('risk', Path(__file__).parents[1] / 'gitops-risk-check.py')
risk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(risk)


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.old = Path(self.tmp.name) / 'old'; self.new = Path(self.tmp.name) / 'new'
        self.appset = {'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'ApplicationSet',
            'metadata': {'name': 'monitoring', 'namespace': 'argocd'}, 'spec': {
                'goTemplate': True, 'goTemplateOptions': ['missingkey=error'],
                'generators': [{'git': {'repoURL': 'https://github.com/mitchross/talos-argocd-proxmox.git',
                    'revision': 'main', 'directories': [{'path': 'monitoring/*'}]}}],
                'template': {'metadata': {'name': 'monitoring-{{ .path.basename }}'}, 'spec': {
                    'project': 'monitoring', 'source': {'path': '{{ .path.path }}'},
                    'destination': {'namespace': '{{ .path.basename }}', 'server': 'https://kubernetes.default.svc'}}}}}
        self.write(self.old / risk.SEED, {'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Application',
            'metadata': {'name': 'root'}, 'spec': {'project': 'default', 'source': {'path': risk.ENTRY}, 'destination': {'namespace': 'argocd'}}})
        self.write(self.old / risk.ENTRY / 'appset.yaml', self.appset)
        self.write(self.old / risk.ENTRY / 'kustomization.yaml', {'resources': ['appset.yaml']})
        self.appdir = 'monitoring/prometheus-stack'
        self.objects = [
            {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'prometheus-stack'}},
            {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim', 'metadata': {'name': 'tsdb'},
             'spec': {'storageClassName': 'longhorn', 'accessModes': ['ReadWriteOnce'], 'resources': {'requests': {'storage': '10Gi'}}}},
            {'apiVersion': 'apps/v1', 'kind': 'StatefulSet', 'metadata': {'name': 'prometheus'}, 'spec': {'replicas': 1}}]
        self.write_app(self.old, self.appdir, self.objects)
        shutil.copytree(self.old, self.new)

    @staticmethod
    def write(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(yaml.safe_dump(obj))

    def write_app(self, root, path, objects):
        (root / path).mkdir(parents=True, exist_ok=True)
        (root / path / 'objects.yaml').write_text(yaml.safe_dump_all(objects))
        self.write(root / path / 'kustomization.yaml', {'namespace': 'prometheus-stack', 'resources': ['objects.yaml']})

    def check(self, changed):
        return risk.inspect(self.old, self.new, changed)[0]

    def test_september_depth_move_final_identity_stable_but_intermediate_disappears(self):
        shutil.move(self.new / self.appdir, self.new / 'prometheus-stack')
        (self.new / 'monitoring/metrics').mkdir()
        shutil.move(self.new / 'prometheus-stack', self.new / 'monitoring/metrics/prometheus-stack')
        updated = copy.deepcopy(self.appset)
        updated['spec']['generators'][0]['git']['directories'][0]['path'] = 'monitoring/*/*'
        self.write(self.new / risk.ENTRY / 'appset.yaml', updated)
        # Prove equal final identities alone would miss this transition.
        a, stand = risk.controllers(self.old); b, newstand = risk.controllers(self.new)
        self.assertEqual(set(risk.inventory(a, stand, risk.directories(self.old))),
                         set(risk.inventory(b, newstand, risk.directories(self.new))))
        findings = self.check([self.appdir + '/objects.yaml', risk.ENTRY + '/appset.yaml'])
        self.assertTrue(any(f['code'] == 'application-disappears' and f['level'] == 'BLOCK'
                            and f['new']['state'] == 'OLD generator + NEW tree' for f in findings))
        old = risk.inventory(a, stand, risk.directories(self.old))
        intermediate = risk.inventory(a, stand, risk.directories(self.new))
        self.assertIn('monitoring-prometheus-stack', old)
        self.assertNotIn('monitoring-prometheus-stack', intermediate)

    def test_depth_race_returns_specific_block_without_render_failure(self):
        # Valid empty category kustomization lets the checker report the precise race.
        shutil.rmtree(self.new / self.appdir)
        self.write_app(self.new, 'monitoring/metrics/prometheus-stack', self.objects)
        self.write(self.new / 'monitoring/metrics/kustomization.yaml', {'resources': ['prometheus-stack']})
        updated = copy.deepcopy(self.appset)
        updated['spec']['generators'][0]['git']['directories'][0]['path'] = 'monitoring/*/*'
        self.write(self.new / risk.ENTRY / 'appset.yaml', updated)
        findings = self.check([risk.ENTRY + '/appset.yaml', self.appdir + '/objects.yaml'])
        self.assertTrue(any(f['code'] == 'application-disappears' and f['target'] == 'monitoring-prometheus-stack'
                            and f['level'] == 'BLOCK' and f['new']['state'] == 'OLD generator + NEW tree' for f in findings))

    def test_persistent_disappearance_and_storage_class(self):
        for kind in ['PersistentVolumeClaim', 'StatefulSet', 'Namespace']:
            with self.subTest(kind=kind):
                self.write_app(self.new, self.appdir, [o for o in self.objects if o['kind'] != kind])
                self.assertTrue(any(f['code'] == 'persistent-resource-disappears' and kind in f['target'] for f in self.check([self.appdir + '/objects.yaml'])))
        updated = copy.deepcopy(self.objects); updated[1]['spec']['storageClassName'] = 'longhorn-wired-ha'
        self.write_app(self.new, self.appdir, updated)
        self.assertTrue(any(f['code'] == 'persistent-spec-storageClassName' for f in self.check([self.appdir + '/objects.yaml'])))

    def test_preservation_and_finalizers(self):
        updated = copy.deepcopy(self.appset); updated['spec']['syncPolicy'] = {'preserveResourcesOnDeletion': True}
        self.write(self.old / risk.ENTRY / 'appset.yaml', updated)
        self.assertTrue(any(f['level'] == 'BLOCK' and f['code'] == 'appset-syncPolicy' for f in self.check([risk.ENTRY + '/appset.yaml'])))
        updated['spec']['template']['metadata']['finalizers'] = ['resources-finalizer.argocd.argoproj.io']
        self.write(self.new / risk.ENTRY / 'appset.yaml', updated)
        self.assertTrue(any(f['code'] == 'application-ownership' for f in self.check([risk.ENTRY + '/appset.yaml'])))

    def test_nonpersistent_finalizer_removed_is_not_resource_disappearance(self):
        old = self.objects + [{'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {
            'name': 'cleanup', 'namespace': 'prometheus-stack', 'finalizers': ['example.org/retain']}}]
        new = copy.deepcopy(old); del new[-1]['metadata']['finalizers']
        self.write_app(self.old, self.appdir, old)
        self.write_app(self.new, self.appdir, new)
        findings = self.check([self.appdir + '/objects.yaml'])
        self.assertTrue(any(f['code'] == 'resource-finalizers' and 'cleanup' in f['target'] for f in findings))
        self.assertFalse(any(f['code'] == 'persistent-resource-disappears' and 'cleanup' in f['target'] for f in findings))

    def test_no_change_and_unsupported_generator(self):
        self.assertEqual([], self.check([]))
        updated = copy.deepcopy(self.appset); updated['spec']['generators'] = [{'matrix': {}}]
        self.write(self.new / risk.ENTRY / 'appset.yaml', updated)
        with self.assertRaisesRegex(ValueError, 'unsupported generator'):
            self.check([risk.ENTRY + '/appset.yaml'])

    def test_leaf_rename_and_owner_change(self):
        shutil.rmtree(self.new / self.appdir)
        self.write_app(self.new, 'monitoring/prometheus-renamed', self.objects)
        findings = self.check([self.appdir + '/objects.yaml'])
        self.assertTrue(any(f['code'] == 'application-disappears' for f in findings))
        self.assertTrue(any(f['code'] == 'resource-owner-transfer' for f in findings))

    def test_category_move_warns_but_preserves_final_identity(self):
        for root in (self.old, self.new):
            shutil.rmtree(root / self.appdir)
        self.write_app(self.old, 'monitoring/metrics/prometheus-stack', self.objects)
        self.write_app(self.new, 'monitoring/logs/prometheus-stack', self.objects)
        updated = copy.deepcopy(self.appset)
        updated['spec']['generators'][0]['git']['directories'][0]['path'] = 'monitoring/*/*'
        for root in (self.old, self.new):
            self.write(root / risk.ENTRY / 'appset.yaml', updated)
        findings = self.check(['monitoring/metrics/prometheus-stack/objects.yaml',
                               'monitoring/logs/prometheus-stack/objects.yaml'])
        self.assertTrue(any(f['code'] == 'application-path' for f in findings))
        self.assertFalse(any(f['code'] == 'application-disappears' for f in findings))
        # The old Application still points at its missing source until reconciliation.
        self.assertTrue(any(f['code'] == 'missing-source-directory' for f in findings))
        self.assertFalse(any(f['level'] == 'BLOCK' for f in findings))

    def test_go_globs_do_not_cross_directory_boundaries(self):
        self.assertFalse(risk.matches('monitoring/metrics/prometheus', 'monitoring/*'))
        self.assertTrue(risk.matches('monitoring/metrics/prometheus', 'monitoring/*/*'))


if __name__ == '__main__':
    unittest.main()
