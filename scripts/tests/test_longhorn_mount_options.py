"""Exercise the PV migration without connecting to Kubernetes."""

import copy
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "infrastructure/storage/longhorn-selinux/scripts/reconcile.py"
CONTEXT = "context=system_u:object_r:ephemeral_t:s0"
CLAIM = "posthog/clickhouse-data-clickhouse-0"


def volume(name="pv-clickhouse", claim=CLAIM, options=None):
    namespace, claim_name = claim.split("/")
    obj = {
        "metadata": {"name": name, "uid": "uid-" + name, "resourceVersion": "10"},
        "spec": {
            "storageClassName": "longhorn-flash",
            "volumeMode": "Filesystem",
            "accessModes": ["ReadWriteOnce"],
            "claimRef": {"namespace": namespace, "name": claim_name, "uid": "claim-uid"},
            "csi": {"driver": "driver.longhorn.io", "fsType": "ext4", "volumeHandle": name},
            "persistentVolumeReclaimPolicy": "Delete",
        },
        "status": {"phase": "Bound"},
    }
    if options is not None:
        obj["spec"]["mountOptions"] = options
    return obj


class MemoryAPI:
    def __init__(self, *volumes):
        self.volumes = {v["metadata"]["name"]: copy.deepcopy(v) for v in volumes}
        self.patches = []
        self.concurrent_change = False

    def list_volumes(self):
        return copy.deepcopy(list(self.volumes.values()))

    def patch_volume(self, name, operations):
        current = self.volumes[name]
        if self.concurrent_change:
            current["metadata"]["resourceVersion"] = "11"
        result = copy.deepcopy(current)
        for op in operations:
            parent, key = op["path"].strip("/").split("/")
            if op["op"] == "test":
                if result[parent].get(key) != op["value"]:
                    raise RuntimeError("concurrent change")
            elif op["op"] == "add":
                result[parent][key] = op["value"]
            elif op["op"] == "remove":
                del result[parent][key]
            else:
                raise AssertionError("Unexpected JSON patch operation")
        self.volumes[name] = result
        self.patches.append((name, operations))


class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location("mount_reconcile", SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)
        else:
            cls.module = None

    def run_migration(self, api, mode="apply", claims=None):
        self.assertIsNotNone(self.module, "PV migration script has not been implemented")
        return self.module.reconcile(api, {"mode": mode, "claims": claims or [CLAIM]})

    def test_changes_only_allowlisted_pv_and_preserves_other_fields(self):
        original = volume(options=["noatime"])
        other = volume("pv-other", "other/data", ["context=other"])
        api = MemoryAPI(original, other)
        self.run_migration(api)
        expected = copy.deepcopy(original)
        expected["spec"]["mountOptions"] = ["noatime", CONTEXT]
        self.assertEqual(api.volumes["pv-clickhouse"], expected)
        self.assertEqual(api.volumes["pv-other"], other)

    def test_adds_missing_options_and_second_run_is_noop(self):
        api = MemoryAPI(volume())
        self.run_migration(api)
        self.run_migration(api)
        self.assertEqual(api.volumes["pv-clickhouse"]["spec"]["mountOptions"], [CONTEXT])
        self.assertEqual(len(api.patches), 1)

    def test_other_selinux_mount_controls_abort_before_any_patch(self):
        for option in ["context=other", "fscontext=other", "defcontext=other", "rootcontext=other"]:
            with self.subTest(option=option):
                api = MemoryAPI(volume(), volume("pv-second", "second/data", [option]))
                with self.assertRaisesRegex(ValueError, "SELinux"):
                    self.run_migration(api, claims=[CLAIM, "second/data"])
                self.assertEqual(api.patches, [])

    def test_refuses_incompatible_target_instead_of_silently_migrating(self):
        changes = [
            {"csi": {"driver": "nfs.csi.k8s.io", "fsType": "ext4"}},
            {"csi": {"driver": "driver.longhorn.io", "fsType": "xfs"}},
            {"csi": {"driver": "driver.longhorn.io"}},
            {"storageClassName": "unreviewed-longhorn"},
            {"volumeMode": "Block"},
            {"accessModes": ["ReadWriteMany"]},
            {"accessModes": ["ReadOnlyMany"]},
        ]
        for change in changes:
            with self.subTest(change=change):
                obj = volume()
                obj["spec"].update(change)
                api = MemoryAPI(obj)
                with self.assertRaises(ValueError):
                    self.run_migration(api)
                self.assertEqual(api.patches, [])

    def test_allows_read_write_once_pod(self):
        obj = volume()
        obj["spec"]["accessModes"] = ["ReadWriteOncePod"]
        api = MemoryAPI(obj)
        self.run_migration(api)
        self.assertEqual(api.volumes["pv-clickhouse"]["spec"]["mountOptions"], [CONTEXT])

    def test_missing_claim_is_safe_on_fresh_cluster(self):
        api = MemoryAPI()
        self.run_migration(api)
        self.assertEqual(api.patches, [])

    def test_released_or_deleting_pv_is_not_modified(self):
        for deleting in [False, True]:
            obj = volume()
            if deleting:
                obj["metadata"]["deletionTimestamp"] = "2026-09-06T00:00:00Z"
            else:
                obj["status"]["phase"] = "Released"
            api = MemoryAPI(obj)
            self.run_migration(api)
            self.assertEqual(api.patches, [])

    def test_plan_mode_does_not_write(self):
        api = MemoryAPI(volume())
        result = self.run_migration(api, mode="plan")
        self.assertEqual(api.patches, [])
        self.assertEqual(len(result), 1)

    def test_rollback_removes_only_our_context_and_is_idempotent(self):
        for options, expected in [(["noatime", CONTEXT], ["noatime"]), ([CONTEXT], None)]:
            api = MemoryAPI(volume(options=options))
            self.run_migration(api, mode="remove")
            self.run_migration(api, mode="remove")
            self.assertEqual(api.volumes["pv-clickhouse"]["spec"].get("mountOptions"), expected)
            self.assertEqual(len(api.patches), 1)

    def test_concurrent_update_fails_without_overwriting_options(self):
        original = volume(options=["noatime"])
        api = MemoryAPI(original)
        api.concurrent_change = True
        with self.assertRaisesRegex(RuntimeError, "concurrent change"):
            self.run_migration(api)
        self.assertEqual(api.volumes["pv-clickhouse"]["spec"], original["spec"])

    def test_invalid_policy_never_writes(self):
        self.assertIsNotNone(self.module, "PV migration script has not been implemented")
        for policy in [{"mode": "apply", "claims": "all"}, {"mode": "apply", "claims": ["*"]}, {"mode": "typo", "claims": [CLAIM]}]:
            api = MemoryAPI(volume())
            with self.assertRaises(ValueError):
                self.module.reconcile(api, policy)
            self.assertEqual(api.patches, [])


if __name__ == "__main__":
    unittest.main()
