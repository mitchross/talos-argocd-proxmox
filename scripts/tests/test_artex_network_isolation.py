"""The artex namespace is cut out of the shared LAN policy and starts from deny-all, and nothing else moves."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICIES = ROOT / "infrastructure/networking/cilium/policies"
NS_KEY = "k8s:io.kubernetes.pod.namespace"


def load(name):
    return yaml.safe_load((POLICIES / name).read_text())


def matches(selector, labels):
    """Kubernetes label-selector semantics, as Cilium's MatchesRequirement applies them."""
    for key, value in (selector.get("matchLabels") or {}).items():
        if labels.get(key) != value:
            return False
    for expr in selector.get("matchExpressions") or []:
        key, op, values = expr["key"], expr["operator"], expr.get("values") or []
        present = key in labels
        if op == "In" and not (present and labels[key] in values):
            return False
        if op == "NotIn" and present and labels[key] in values:
            return False
        if op == "Exists" and not present:
            return False
        if op == "DoesNotExist" and present:
            return False
    return True


ARTEX_POD = {NS_KEY: "artex", "k8s:app.kubernetes.io/name": "artex"}
ARTEX_MOVER = {NS_KEY: "artex", "k8s:app.kubernetes.io/managed-by": "kopiur"}
OTHER_PODS = [
    {NS_KEY: "default"},
    {NS_KEY: "hermes", "k8s:app.kubernetes.io/name": "hermes"},
    {NS_KEY: "artex-other"},
    {NS_KEY: "kube-system", "k8s:k8s-app": "kube-dns"},
]
# Endpoints with no namespace label, e.g. the gateway envoy.
RESERVED = [{"reserved:ingress": ""}, {"reserved:health": ""}]


class SharedPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = load("block-lan-access.yaml")
        self.selector = self.policy["spec"]["endpointSelector"]

    def test_excludes_only_artex(self):
        self.assertEqual(self.selector, {"matchExpressions": [
            {"key": NS_KEY, "operator": "NotIn", "values": ["artex"]}]})
        self.assertFalse(matches(self.selector, ARTEX_POD))
        self.assertFalse(matches(self.selector, ARTEX_MOVER))

    def test_every_other_endpoint_keeps_the_shared_policy(self):
        for labels in OTHER_PODS + RESERVED:
            with self.subTest(labels=labels):
                self.assertTrue(matches(self.selector, labels))

    def test_rules_unchanged_apart_from_selector(self):
        spec = self.policy["spec"]
        self.assertEqual(spec["ingress"], [{"fromEntities": ["cluster", "host", "world"]}])
        self.assertEqual(spec["egress"][0]["toCIDRSet"][0]["cidr"], "0.0.0.0/0")
        self.assertEqual(spec["egress"][1], {"toEntities": ["cluster", "host", "kube-apiserver"]})


class ArtexBaselineTest(unittest.TestCase):
    def setUp(self):
        self.policy = load("artex-namespace-baseline.yaml")
        self.spec = self.policy["spec"]

    def test_kind_and_listed(self):
        self.assertEqual(self.policy["kind"], "CiliumClusterwideNetworkPolicy")
        kustomization = yaml.safe_load((ROOT / "infrastructure/networking/cilium/kustomization.yaml").read_text())
        self.assertIn("policies/artex-namespace-baseline.yaml", kustomization["resources"])

    def test_selects_only_artex(self):
        selector = self.spec["endpointSelector"]
        self.assertEqual(selector, {"matchLabels": {NS_KEY: "artex"}})
        self.assertTrue(matches(selector, ARTEX_POD))
        self.assertTrue(matches(selector, ARTEX_MOVER))
        for labels in OTHER_PODS + RESERVED:
            with self.subTest(labels=labels):
                self.assertFalse(matches(selector, labels))

    def test_every_artex_endpoint_is_covered_by_exactly_one_side(self):
        shared = load("block-lan-access.yaml")["spec"]["endpointSelector"]
        for labels in [ARTEX_POD, ARTEX_MOVER] + OTHER_PODS + RESERVED:
            with self.subTest(labels=labels):
                self.assertNotEqual(matches(shared, labels), matches(self.spec["endpointSelector"], labels))

    def test_default_deny_both_ways(self):
        self.assertEqual(self.spec["enableDefaultDeny"], {"ingress": True, "egress": True})
        self.assertEqual(self.spec["ingress"], [{}])
        for field in ("ingressDeny", "egressDeny", "nodeSelector"):
            self.assertNotIn(field, self.spec)

    def test_egress_is_dns_to_kube_dns_only(self):
        self.assertEqual(self.spec["egress"], [{
            "toEndpoints": [{"matchLabels": {NS_KEY: "kube-system", "k8s:k8s-app": "kube-dns"}}],
            "toPorts": [{"ports": [{"port": "53", "protocol": "UDP"}, {"port": "53", "protocol": "TCP"}]}],
        }])


if __name__ == "__main__":
    unittest.main()
