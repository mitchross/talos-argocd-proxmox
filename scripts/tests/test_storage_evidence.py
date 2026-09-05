"""Offline tests: subprocesses are mocked; no Kubernetes or host disks are queried."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("storage_evidence", Path(__file__).parents[1] / "collect-storage-evidence.py")
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def source(*objects):
    return {"status": "collected", "data": {"items": list(objects)}}


def fixture():
    return {
        "nodes": source({"metadata": {"name": "worker-a", "labels": {"topology.kubernetes.io/zone": "host-a"}}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}),
        "claims": source({"metadata": {"name": "db", "namespace": "app", "annotations": {"private": "do-not-export"}}, "spec": {"volumeName": "pv-a", "storageClassName": "longhorn-wired-ha"}, "status": {"phase": "Bound"}}),
        "persistentvolumes": source({"metadata": {"name": "pv-a"}, "spec": {"csi": {"driver": "driver.longhorn.io", "volumeHandle": "vol-a", "volumeAttributes": {"secret": "do-not-export"}}}}),
        "longhorn_volumes": source({"metadata": {"name": "vol-a"}, "spec": {"numberOfReplicas": 2}, "status": {"state": "attached", "robustness": "degraded"}}),
        "longhorn_replicas": source({"metadata": {"name": "replica-a"}, "spec": {"volumeName": "vol-a", "nodeID": "worker-a", "diskID": "disk-a"}, "status": {"currentState": "running"}}),
        "longhorn_nodes": source(),
    }


class StorageEvidenceTests(unittest.TestCase):
    def test_claim_to_volume_to_replica_mapping(self):
        result = evidence.summarize_cluster(fixture())
        volume = result["claims"][0]["longhorn"]
        self.assertEqual(volume["volume"], "vol-a")
        self.assertEqual(volume["robustness"], "degraded")
        self.assertEqual(volume["observed_zones"], ["host-a"])
        self.assertEqual(volume["desired_replicas"], 2)
        self.assertEqual(len(volume["replica_placement"]), 1)

    def test_unavailable_data_stays_unknown(self):
        raw = fixture()
        raw["longhorn_volumes"] = {"status": "unavailable"}
        self.assertIsNone(evidence.summarize_cluster(raw)["claims"][0]["longhorn"])

    def test_sensitive_unrelated_fields_are_not_exported(self):
        self.assertNotIn("do-not-export", json.dumps(evidence.summarize_cluster(fixture())))

    def test_missing_zone_is_not_a_new_failure_domain(self):
        raw = fixture()
        raw["nodes"] = source()
        result = evidence.summarize_cluster(raw)["claims"][0]["longhorn"]
        self.assertEqual(result["observed_zones"], [])
        self.assertEqual(result["unknown_zone_replicas"], 1)

    def test_non_longhorn_csi_is_not_guessed(self):
        raw = fixture()
        raw["persistentvolumes"]["data"]["items"][0]["spec"]["csi"]["driver"] = "nfs.csi.k8s.io"
        self.assertIsNone(evidence.summarize_cluster(raw)["claims"][0]["longhorn"])

    def test_condition_mapping_supports_core_and_longhorn(self):
        self.assertEqual(evidence.conditions({"status": {"conditions": {"ready": {"type": "Ready", "status": "False"}}}}), {"Ready": "False"})
        self.assertEqual(evidence.conditions({}), {})

    def test_run_failure_does_not_include_stderr(self):
        process = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"secret-do-not-export")
        with patch.object(evidence.subprocess, "run", return_value=process):
            result = evidence.run(["kubectl", "get", "nodes"])
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("secret-do-not-export", str(result))

    def test_missing_command(self):
        with patch.object(evidence.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(evidence.run(["iostat"])["status"], "unavailable")

    def test_timeout(self):
        with patch.object(evidence.subprocess, "run", side_effect=subprocess.TimeoutExpired("kubectl", 20)):
            self.assertEqual(evidence.run(["kubectl"])["status"], "unavailable")

    def test_json_and_size_limits(self):
        process = subprocess.CompletedProcess([], 0, stdout=b"not json", stderr=b"")
        with patch.object(evidence.subprocess, "run", return_value=process):
            self.assertEqual(evidence.run(["example"])["status"], "unavailable")
        process.stdout = b'{"ok":true}'
        with patch.object(evidence.subprocess, "run", return_value=process), patch.object(evidence, "MAX_OUTPUT", 2):
            self.assertEqual(evidence.run(["example"])["status"], "unavailable")

    def test_cluster_only_uses_get_and_explicit_context(self):
        with patch.object(evidence, "run", return_value=source()) as runner:
            result = evidence.collect_cluster("chosen-context")
        self.assertTrue(result["not_proven"])
        for call in runner.call_args_list:
            args = call.args[0]
            self.assertEqual(args[:5], ["kubectl", "--context", "chosen-context", "--request-timeout=15s", "get"])
            self.assertNotIn("secrets", args)
            self.assertNotIn("configmaps", args)

    def test_host_uses_fixed_read_only_inventory_commands(self):
        with patch.object(evidence, "run", return_value={"status": "unavailable"}) as runner:
            result = evidence.collect_host()
        self.assertEqual({call.args[0][0] for call in runner.call_args_list}, {"lsblk", "vgs", "lvs", "iostat"})
        self.assertEqual(len(result["collection"]), 4)

    def test_private_file_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            evidence.write_report(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text()), {"ok": True})
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                evidence.write_report(path, {"overwritten": True})
            self.assertEqual(json.loads(path.read_text()), {"ok": True})

    def test_cli_refuses_implicit_cluster_context(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([os.sys.executable, str(SPEC.origin), "cluster", "--output", str(Path(directory) / "report.json")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires --context", result.stderr)


if __name__ == "__main__":
    unittest.main()
