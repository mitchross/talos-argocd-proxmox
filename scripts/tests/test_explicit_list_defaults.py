import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "explicit_list_defaults", Path(__file__).parents[1] / "validate-explicit-list-defaults.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def route(parent=None, backend=None):
    parent = {"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": "gw"} if parent is None else parent
    backend = {"group": "", "kind": "Service", "name": "web", "port": 80, "weight": 1} if backend is None else backend
    return {
        "apiVersion": "gateway.networking.k8s.io/v1",
        "kind": "HTTPRoute",
        "metadata": {"name": "r", "namespace": "ns"},
        "spec": {"parentRefs": [parent], "rules": [{"backendRefs": [backend]}]},
    }


def policy(source):
    return {
        "apiVersion": "kopiur.home-operations.com/v1alpha1",
        "kind": "SnapshotPolicy",
        "metadata": {"name": "p", "namespace": "ns"},
        "spec": {"sources": [source]},
    }


class ExplicitListDefaultsTest(unittest.TestCase):
    def test_complete_route_passes(self):
        self.assertEqual(module.validate([route()]), [])

    def test_parent_ref_missing_group_and_kind_fails(self):
        self.assertEqual(len(module.validate([route(parent={"name": "gw"})])), 2)

    def test_backend_ref_missing_weight_fails(self):
        errors = module.validate([route(backend={"group": "", "kind": "Service", "name": "web"})])
        self.assertEqual(len(errors), 1)
        self.assertIn("weight", errors[0])

    def test_filter_only_rule_passes(self):
        doc = route()
        doc["spec"]["rules"] = [{"filters": [{"type": "RequestRedirect"}]}]
        self.assertEqual(module.validate([doc]), [])

    def test_snapshot_policy_source_defaults(self):
        ok = {"pvc": {"name": "x"}, "sourcePathStrategy": "PvcName", "readOnly": True}
        self.assertEqual(module.validate([policy(ok)]), [])
        self.assertEqual(len(module.validate([policy({"pvc": {"name": "x"}})])), 2)

    def test_load_docs_skips_unparseable_unrelated_documents(self):
        text = "kind: ConfigMap\ndata:\n  a: !!value x\n---\nkind: HTTPRoute\nmetadata:\n  name: r\n"
        self.assertEqual(len(module.load_docs(text)), 1)


if __name__ == "__main__":
    unittest.main()
