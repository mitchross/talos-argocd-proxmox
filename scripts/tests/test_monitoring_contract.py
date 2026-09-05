import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("monitoring_contract", Path(__file__).parents[1] / "validate-monitoring-contract.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def healthy_objects():
    objects = []
    for monitor, service in contract.MONITORS.items():
        objects.extend([
            {"kind": "ServiceMonitor", "metadata": {"name": monitor, "namespace": "prometheus-stack"},
             "spec": {"namespaceSelector": {"matchNames": ["kube-system"]},
                      "selector": {"matchLabels": {"app": service}}, "endpoints": [{"port": "metrics"}]}},
            {"kind": "Service", "metadata": {"name": service, "namespace": "kube-system", "labels": {"app": service}},
             "spec": {"ports": [{"name": "metrics", "targetPort": "prometheus"}]}},
        ])
    for kind, name in [("DaemonSet", "kube-prometheus-stack-prometheus-node-exporter"),
                       ("Deployment", "kube-prometheus-stack-kube-state-metrics")]:
        objects.append({"kind": kind, "metadata": {"name": name, "namespace": "prometheus-stack"},
                        "spec": {"template": {"spec": {"containers": [{"name": "exporter", "resources": {
                            "requests": {"cpu": "50m", "memory": "128Mi"}, "limits": {"memory": "256Mi"}}}]}}}})
    return objects


class MonitoringContractTests(unittest.TestCase):
    def test_valid_and_repeated_nested_render(self):
        objects = healthy_objects()
        self.assertEqual(contract.validate(objects + copy.deepcopy(objects)), [])

    def test_missing_service_is_not_healthy_discovery(self):
        objects = healthy_objects()
        del objects[1]
        self.assertTrue(contract.validate(objects))

    def test_target_port_is_not_service_port(self):
        objects = healthy_objects()
        objects[0]["spec"]["endpoints"][0]["port"] = "prometheus"
        self.assertTrue(contract.validate(objects))

    def test_wrong_service_labels_or_namespace_fail(self):
        for field in ["labels", "namespace"]:
            objects = healthy_objects()
            objects[1]["metadata"][field] = {} if field == "labels" else "gateway"
            self.assertTrue(contract.validate(objects))

    def test_wrong_monitor_namespace_selection_fails(self):
        objects = healthy_objects()
        objects[0]["spec"]["namespaceSelector"]["matchNames"] = ["gateway"]
        self.assertTrue(contract.validate(objects))

    def test_ignored_helm_resource_values_fail(self):
        for resources in [None, {}, {"limits": {"memory": "256Mi"}}]:
            objects = healthy_objects()
            objects[-1]["spec"]["template"]["spec"]["containers"][0]["resources"] = resources
            self.assertTrue(contract.validate(objects))


if __name__ == "__main__":
    unittest.main()
