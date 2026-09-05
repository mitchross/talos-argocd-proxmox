"""Offline regression cases; these fixtures are not deployable applications."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

SCRIPT = Path(__file__).parents[1] / "validate-kopiur-coverage.py"
GROUP = "kopiur.home-operations.com"
NS = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "test", "labels": {f"{GROUP}/repo": "cluster-kopia"}}}
PVC = {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"namespace": "test", "name": "data"}, "spec": {"storageClassName": "longhorn", "dataSourceRef": {"apiGroup": GROUP, "kind": "Restore", "name": "data-restore"}}}
POLICY = {"apiVersion": f"{GROUP}/v1alpha1", "kind": "SnapshotPolicy", "metadata": {"namespace": "test", "name": "data-policy"}, "spec": {"sources": [{"pvc": {"name": "data"}}], "mover": {"securityContext": {"runAsUser": 999}}}}
RESTORE = {"apiVersion": f"{GROUP}/v1alpha1", "kind": "Restore", "metadata": {"namespace": "test", "name": "data-restore"}, "spec": {"source": {"fromPolicy": {"name": "data-policy"}}, "target": {"populator": {}}, "mover": {"securityContext": {"runAsUser": 999}}}}


def run(*docs):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "rendered.yaml"
        path.write_text(yaml.safe_dump_all(docs))
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)


class KopiurCoverageTest(unittest.TestCase):
    def test_correct_populator(self):
        self.assertEqual(run(NS, PVC, POLICY, RESTORE).returncode, 0)

    def test_absent_named_restore(self):
        result = run(NS, PVC, POLICY)
        self.assertEqual(result.returncode, 1)
        self.assertIn("named Restore", result.stdout)

    def test_wrong_policy(self):
        restore = deepcopy(RESTORE)
        restore["spec"]["source"]["fromPolicy"]["name"] = "wrong"
        self.assertEqual(run(NS, PVC, POLICY, restore).returncode, 1)

    def test_wrong_restore_namespace(self):
        restore = deepcopy(RESTORE)
        restore["metadata"]["namespace"] = "other"
        self.assertEqual(run(NS, PVC, POLICY, restore).returncode, 1)

    def test_cross_namespace_pointer(self):
        pvc = deepcopy(PVC)
        pvc["spec"]["dataSourceRef"]["namespace"] = "other"
        self.assertEqual(run(NS, pvc, POLICY, RESTORE).returncode, 1)

    def test_not_a_populator(self):
        restore = deepcopy(RESTORE)
        restore["spec"]["target"] = {"pvc": {"name": "other"}}
        self.assertEqual(run(NS, PVC, POLICY, restore).returncode, 1)

    def test_missing_pointer_still_fails(self):
        pvc = deepcopy(PVC)
        del pvc["spec"]["dataSourceRef"]
        self.assertEqual(run(NS, pvc, POLICY, RESTORE).returncode, 1)

    def test_all_storage_classes_receive_coverage_review(self):
        for storage in ("longhorn", "longhorn-flash", "longhorn-wired-ha", "truenas-nfs", "custom-local"):
            with self.subTest(storage=storage):
                pvc = deepcopy(PVC)
                pvc["spec"] = {"storageClassName": storage}
                result = run(NS, pvc)
                self.assertEqual(result.returncode, 0)
                self.assertIn("[gap]", result.stdout)
                self.assertIn(storage, result.stdout)

    def test_reasoned_exemption(self):
        pvc = deepcopy(PVC)
        pvc["spec"] = {"storageClassName": "longhorn-flash"}
        pvc["metadata"].update(labels={"backup-exempt": "true"}, annotations={"storage.vanillax.dev/backup-exempt-reason": "Regenerable cache"})
        result = run(NS, pvc)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("WARN", result.stdout)

    def test_exemption_cannot_hide_dangling_restore(self):
        pvc = deepcopy(PVC)
        pvc["metadata"]["labels"] = {"backup-exempt": "true"}
        self.assertEqual(run(NS, pvc).returncode, 1)

    def test_direct_operator_restore_keeps_working(self):
        restore = deepcopy(RESTORE)
        restore["spec"]["target"] = {"pvc": {"name": "data"}}
        self.assertEqual(run(NS, POLICY, restore).returncode, 0)
        restore["spec"]["source"]["fromPolicy"]["name"] = "wrong"
        self.assertEqual(run(NS, POLICY, restore).returncode, 1)

    def test_explicit_manual_operator_recovery_keeps_working(self):
        policy = deepcopy(POLICY)
        policy["metadata"]["annotations"] = {"storage.vanillax.dev/operator-owned-pvc": "true", "storage.vanillax.dev/no-restore-before-bind-reason": "Manual operator recovery is documented"}
        result = run(NS, policy)
        self.assertEqual(result.returncode, 0)
        self.assertIn("manual step", result.stdout)

    def test_aggregate_duplicate_objects_do_not_create_false_errors(self):
        self.assertEqual(run(NS, PVC, POLICY, RESTORE, NS, PVC, POLICY, RESTORE).returncode, 0)

    def test_missing_namespace_label_still_fails(self):
        ns = deepcopy(NS)
        ns["metadata"]["labels"] = {}
        self.assertEqual(run(ns, PVC, POLICY, RESTORE).returncode, 1)


if __name__ == "__main__":
    unittest.main()
