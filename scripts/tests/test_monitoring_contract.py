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
    for kind, namespace, name in [
        ("DaemonSet", "prometheus-stack", "kube-prometheus-stack-prometheus-node-exporter"),
        ("Deployment", "prometheus-stack", "kube-prometheus-stack-kube-state-metrics"),
        ("DaemonSet", "kube-system", "cilium-envoy"),
        ("Deployment", "external-secrets", "external-secrets"),
        ("Deployment", "snapshot-controller", "snapshot-controller"),
    ]:
        objects.append({"kind": kind, "metadata": {"name": name, "namespace": namespace},
                        "spec": {"template": {"spec": {"containers": [{"name": "exporter", "resources": {
                            "requests": {"cpu": "50m", "memory": "128Mi"}, "limits": {"memory": "256Mi"}}}]}}}})
    snapshot = objects[-1]["spec"]
    snapshot["replicas"] = 2
    snapshot["template"]["spec"]["affinity"] = {"podAntiAffinity": {
        "preferredDuringSchedulingIgnoredDuringExecution": [{"weight": 100,
            "podAffinityTerm": {"topologyKey": "topology.kubernetes.io/zone"}}]}}
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

    def test_ignored_snapshot_replica_or_affinity_values_fail(self):
        for field in ["replicas", "affinity"]:
            objects = healthy_objects()
            spec = objects[-1]["spec"]
            if field == "replicas":
                spec["replicas"] = 1
            else:
                spec["template"]["spec"].pop("affinity")
            self.assertTrue(contract.validate(objects))

    def test_ignored_helm_resource_values_fail(self):
        for resources in [None, {}, {"limits": {"memory": "256Mi"}}]:
            objects = healthy_objects()
            objects[-1]["spec"]["template"]["spec"]["containers"][0]["resources"] = resources
            self.assertTrue(contract.validate(objects))


class DatabaseDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.objects = []
        for ns in contract.DATABASES:
            self.objects.extend([
                {"kind": "Deployment", "metadata": {"name": "database", "namespace": ns},
                 "spec": {"template": {"metadata": {"labels": {"app": "database"}}, "spec": {
                     "containers": [{"name": "postgres-exporter", "ports": [{"name": "metrics", "containerPort": 9187}],
                                     "env": [{"name": "DATA_SOURCE_URI", "value": "127.0.0.1:5432/app"},
                                             {"name": "DATA_SOURCE_PASS", "valueFrom": {"secretKeyRef": {"name": "db", "key": "password"}}}]}]}}}},
                {"kind": "Service", "metadata": {"name": "db-metrics", "namespace": ns, "labels": {"app": "database"}},
                 "spec": {"selector": {"app": "database"}, "ports": [{"name": "metrics", "port": 9187, "targetPort": "metrics"}]}},
                {"kind": "ServiceMonitor", "metadata": {"name": "database", "namespace": ns},
                 "spec": {"selector": {"matchLabels": {"app": "database"}}, "endpoints": [{"port": "metrics"}]}},
            ])

    def test_all_databases_and_duplicate_nested_renders(self):
        self.assertEqual(contract.validate_databases(self.objects + copy.deepcopy(self.objects)), [])

    def test_missing_service_labels_reproduces_posthog_blind_spot(self):
        service = next(o for o in self.objects if o["kind"] == "Service" and o["metadata"]["namespace"] == "posthog")
        service["metadata"].pop("labels")
        self.assertTrue(any("posthog" in e for e in contract.validate_databases(self.objects)))

    def test_wrong_pod_selector_or_target_port_fails(self):
        for key, value in [("selector", {"app": "wrong"}), ("ports", [{"name": "metrics", "port": 9187, "targetPort": "wrong"}])]:
            objects = copy.deepcopy(self.objects)
            next(o for o in objects if o["kind"] == "Service")["spec"][key] = value
            self.assertTrue(contract.validate_databases(objects))

    def test_missing_exporter_and_duplicate_scrapes_fail(self):
        objects = [o for o in self.objects if not (o["kind"] == "Deployment" and o["metadata"]["namespace"] == "keep")]
        self.assertTrue(contract.validate_databases(objects))
        extra = copy.deepcopy(next(o for o in self.objects if o["kind"] == "ServiceMonitor"))
        extra["metadata"]["name"] = "duplicate"
        self.assertTrue(contract.validate_databases(self.objects + [extra]))

    def test_exporter_does_not_gate_database_readiness(self):
        workload = next(o for o in self.objects if o["kind"] == "Deployment" and o["metadata"]["namespace"] == "keep")
        workload["spec"]["template"]["spec"]["containers"][0]["readinessProbe"] = {"httpGet": {"port": "metrics"}}
        self.assertTrue(any("readiness" in e for e in contract.validate_databases(self.objects)))

    def test_monitor_expressions_must_not_be_ignored(self):
        monitor = next(o for o in self.objects if o["kind"] == "ServiceMonitor")
        monitor["spec"]["selector"]["matchExpressions"] = [
            {"key": "app", "operator": "NotIn", "values": ["database"]}]
        self.assertTrue(contract.validate_databases(self.objects))

    def test_expression_only_and_empty_selector_follow_kubernetes_semantics(self):
        monitor = next(o for o in self.objects if o["kind"] == "ServiceMonitor")
        for selector in ({}, {"matchExpressions": [
                {"key": "app", "operator": "In", "values": ["database"]}]}):
            monitor["spec"]["selector"] = selector
            self.assertEqual(contract.validate_databases(self.objects), [])

    def test_cross_namespace_monitor_requires_explicit_selection(self):
        monitor = next(o for o in self.objects if o["kind"] == "ServiceMonitor")
        original_namespace = monitor["metadata"]["namespace"]
        monitor["metadata"]["namespace"] = "central-monitoring"
        self.assertTrue(contract.validate_databases(self.objects))
        monitor["spec"]["namespaceSelector"] = {"matchNames": [original_namespace]}
        self.assertEqual(contract.validate_databases(self.objects), [])

    def test_service_based_connection_and_plaintext_password_fail(self):
        workload = next(o for o in self.objects if o["kind"] == "Deployment" and o["metadata"]["namespace"] == "keep")
        workload["spec"]["template"]["spec"]["containers"][0]["env"] = [
            {"name": "DATA_SOURCE_URI", "value": "database:5432/app"},
            {"name": "DATA_SOURCE_PASS", "value": "fixture"},
        ]
        self.assertEqual(len(contract.validate_databases(self.objects)), 2)


if __name__ == "__main__":
    unittest.main()
