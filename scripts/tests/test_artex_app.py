"""ARTEX stays internal, keyless and closed: guards for the security properties of its manifests."""
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
# Staged under proposals/ until the image is published and the namespace baseline is live.
APP = next(p for p in (ROOT / "my-apps/development/artex", ROOT / "proposals/artex") if p.is_dir())


def render():
    out = subprocess.run(["kustomize", "build", str(APP)], check=True, capture_output=True, text=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


class ArtexManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = render()

    def get(self, kind, name):
        return next(d for d in self.docs if d["kind"] == kind and d["metadata"]["name"] == name)

    def of_kind(self, kind):
        return [d for d in self.docs if d["kind"] == kind]

    def test_server_identity_and_flags(self):
        pod = self.get("Deployment", "artex")["spec"]["template"]["spec"]
        self.assertIs(pod["automountServiceAccountToken"], False)
        for field in ("hostNetwork", "hostPID", "hostIPC", "serviceAccountName"):
            self.assertNotIn(field, pod)
        self.assertNotIn("fsGroup", pod["securityContext"])
        self.assertEqual(pod["securityContext"]["seccompProfile"], {"type": "RuntimeDefault"})
        (container,) = pod["containers"]
        sc = container["securityContext"]
        self.assertIs(sc["allowPrivilegeEscalation"], False)
        self.assertEqual(sc["capabilities"]["drop"], ["ALL"])
        self.assertEqual(sorted(sc["capabilities"]["add"]),
                         ["CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID", "KILL", "SETGID", "SETUID"])
        args = container["args"]
        self.assertEqual(args[args.index("-proxy") + 1], "127.0.0.1:8788")
        self.assertEqual(args[args.index("-exec-uid") + 1], "10001")
        self.assertEqual(args[args.index("-exec-gid") + 1], "10001")
        self.assertEqual([p["containerPort"] for p in container["ports"]], [8787])
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertTrue(all("persistentVolumeClaim" in v for v in volumes.values()))
        self.assertEqual(sorted(m["mountPath"] for m in container["volumeMounts"]), ["/app/data", "/app/keys"])

    def test_rwo_singletons_never_surge(self):
        for dep in self.of_kind("Deployment"):
            with self.subTest(dep["metadata"]["name"]):
                self.assertEqual(dep["spec"]["replicas"], 1)
                self.assertEqual(dep["spec"]["strategy"]["rollingUpdate"]["maxSurge"], 0)

    def test_only_the_ui_is_routed_internally(self):
        ports = [p["port"] for s in self.of_kind("Service") for p in s["spec"]["ports"]]
        self.assertNotIn(8788, ports)
        (route,) = self.of_kind("HTTPRoute")
        self.assertNotIn("labels", route["metadata"])
        self.assertEqual(route["spec"]["parentRefs"], [{
            "group": "gateway.networking.k8s.io", "kind": "Gateway", "name": "gateway-internal-technitium",
            "namespace": "gateway", "sectionName": "https"}])
        self.assertEqual(route["spec"]["hostnames"], ["artex.vanillax.me"])

    def test_llm_is_local_vllm_without_keys(self):
        (cm,) = self.of_kind("ConfigMap")
        data = cm["data"]
        self.assertEqual(data["ARTEX_LLM_PROVIDER"], "ollama")
        self.assertEqual(data["ARTEX_LLM_BASE_URL"], "http://vllm-service.vllm.svc.cluster.local:8080/v1")
        self.assertEqual(data["ARTEX_LLM_PRIVATE_ENDPOINTS"], "vllm-service.vllm.svc.cluster.local:8080")
        self.assertEqual(data["ARTEX_UPDATE_CHECK"], "0")
        env = self.get("Deployment", "artex")["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertEqual([e["name"] for e in env], ["ARTEX_PG_DSN"])
        (es,) = self.of_kind("ExternalSecret")
        self.assertEqual([d["remoteRef"]["property"] for d in es["spec"]["data"]], ["artex_db_password"])

    def test_policies_allow_no_world_or_cluster(self):
        for cnp in self.of_kind("CiliumNetworkPolicy"):
            spec = cnp["spec"]
            for rule in spec.get("ingress", []) + spec.get("egress", []):
                with self.subTest(cnp["metadata"]["name"]):
                    for field in ("fromEntities", "toEntities"):
                        self.assertFalse(set(rule.get(field, [])) & {"all", "world", "cluster", "host", "remote-node"})
                    self.assertNotIn("toFQDNs", rule)
                    self.assertTrue(rule.get("toPorts"), "every rule names its ports")
        cidrs = [c for cnp in self.of_kind("CiliumNetworkPolicy") for r in cnp["spec"].get("egress", [])
                 for c in r.get("toCIDR", []) + [s["cidr"] for s in r.get("toCIDRSet", [])]]
        self.assertEqual(cidrs, ["192.168.10.133/32"])
        movers = self.get("CiliumNetworkPolicy", "artex-kopiur-movers")["spec"]
        self.assertEqual(movers["endpointSelector"], {"matchLabels": {"app.kubernetes.io/managed-by": "kopiur"}})

    def test_every_pvc_is_backed_up(self):
        pvcs = {p["metadata"]["name"] for p in self.of_kind("PersistentVolumeClaim")}
        sources = {s["pvc"]["name"] for p in self.of_kind("SnapshotPolicy") for s in p["spec"]["sources"]}
        self.assertEqual(pvcs, sources)
        self.assertEqual(pvcs, {"artex-data", "artex-keys", "artex-postgres-16-data"})


if __name__ == "__main__":
    unittest.main()
