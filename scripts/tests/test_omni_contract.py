"""Synthetic Omni contracts; no API, VM, disk or credential is accessed."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

import yaml

SPEC = importlib.util.spec_from_file_location("omni_contract", Path(__file__).parents[1] / "validate-omni-contract.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def fixtures():
    data = {"cores": 4, "sockets": 1, "memory": 8192, "disk_size": 100, "storage_selector": 'name == "cp-storage"'}
    classes = {"cp": {"metadata": {"id": "cp", "type": "MachineClasses.omni.sidero.dev"}, "spec": {"autoprovision": {"providerid": "host-a", "providerdata": yaml.safe_dump(data)}}}}
    documents = [{"kind": "Cluster", "name": "test"}, {"kind": "ControlPlane", "machineClass": {"name": "cp", "size": 1}, "patches": [{"inline": {"machine": {"nodeLabels": {contract.ZONE: "host-a", contract.LINK: "wired"}}}}]}]
    return documents, classes


class OmniContractTests(unittest.TestCase):
    def test_valid_contract_and_declared_budget(self):
        errors, totals = contract.validate(*fixtures())
        self.assertEqual(errors, [])
        self.assertEqual(totals["host-a"]["memory_mib"], 8192)
        self.assertEqual(totals["host-a"]["vcpus"], 4)

    def test_missing_class(self):
        docs, classes = fixtures()
        self.assertTrue(contract.validate(docs, {})[0])

    def test_machine_identity(self):
        docs, classes = fixtures()
        classes["cp"]["metadata"]["id"] = "not-cp"
        self.assertTrue(contract.validate(docs, classes)[0])

    def test_invalid_size_and_boolean(self):
        for value in (0, -1, True, "2"):
            with self.subTest(value=value):
                docs, classes = fixtures()
                docs[1]["machineClass"]["size"] = value
                self.assertTrue(contract.validate(docs, classes)[0])

    def test_invalid_providerdata_does_not_echo_payload(self):
        docs, classes = fixtures()
        classes["cp"]["spec"]["autoprovision"]["providerdata"] = "[not-a-mapping, sensitive-value]"
        errors, _ = contract.validate(docs, classes)
        self.assertTrue(errors)
        self.assertNotIn("sensitive-value", str(errors))

    def test_same_host_cannot_claim_two_failure_domains(self):
        docs, classes = fixtures()
        worker = deepcopy(docs[1])
        worker.update(kind="Workers", name="worker")
        worker["patches"][0]["inline"]["machine"]["nodeLabels"][contract.ZONE] = "invented-zone"
        docs.append(worker)
        self.assertTrue(any("multiple physical-host zones" in e for e in contract.validate(docs, classes)[0]))

    def test_multiple_guests_same_host_same_zone(self):
        docs, classes = fixtures()
        worker = deepcopy(docs[1])
        worker.update(kind="Workers", name="worker")
        docs.append(worker)
        errors, totals = contract.validate(docs, classes)
        self.assertFalse(errors)
        self.assertEqual(totals["host-a"]["machines"], 2)
        self.assertEqual(totals["host-a"]["memory_mib"], 16384)

    def test_missing_control_plane_and_zone(self):
        docs, classes = fixtures()
        self.assertTrue(contract.validate(docs[:1], classes)[0])
        del docs[1]["patches"][0]["inline"]["machine"]["nodeLabels"][contract.ZONE]
        self.assertTrue(contract.validate(docs, classes)[0])

    def test_wifi_requires_taint_and_unschedulable_disks(self):
        docs, classes = fixtures()
        machine = docs[1]["patches"][0]["inline"]["machine"]
        machine["nodeLabels"][contract.LINK] = "wifi"
        self.assertTrue(contract.validate(docs, classes)[0])
        machine["nodeTaints"] = {contract.LINK: "wifi:NoSchedule"}
        machine["nodeAnnotations"] = {contract.DISKS: '[{"name":"data","path":"/var/mnt/data","allowScheduling":true}]'}
        self.assertTrue(contract.validate(docs, classes)[0])
        machine["nodeAnnotations"][contract.DISKS] = '[{"name":"data","path":"/var/mnt/data","allowScheduling":false}]'
        self.assertFalse(contract.validate(docs, classes)[0])
        machine["nodeAnnotations"]["node.longhorn.io/default-node-tags"] = '["wired-storage"]'
        self.assertTrue(contract.validate(docs, classes)[0])

    def test_duplicate_or_relative_longhorn_paths(self):
        for declaration in ('[{"name":"a","path":"relative"}]', '[{"name":"a","path":"/data"},{"name":"b","path":"/data"}]'):
            docs, classes = fixtures()
            docs[1]["patches"][0]["inline"]["machine"]["nodeAnnotations"] = {contract.DISKS: declaration}
            self.assertTrue(contract.validate(docs, classes)[0])

    def test_invalid_disk_and_memory_budget(self):
        for field in ("memory", "cores", "disk_size"):
            docs, classes = fixtures()
            data = yaml.safe_load(classes["cp"]["spec"]["autoprovision"]["providerdata"])
            data[field] = -1
            classes["cp"]["spec"]["autoprovision"]["providerdata"] = yaml.safe_dump(data)
            self.assertTrue(contract.validate(docs, classes)[0])

    def test_duplicate_machine_set(self):
        docs, classes = fixtures()
        docs.append(deepcopy(docs[1]))
        self.assertTrue(any("Duplicate" in e for e in contract.validate(docs, classes)[0]))


if __name__ == "__main__":
    unittest.main()
