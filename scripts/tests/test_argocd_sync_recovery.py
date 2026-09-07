"""Check source policy and the actual Helm/Kustomize output; never contact a cluster."""
from copy import deepcopy
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
ARGO = ROOT / "infrastructure/controllers/argocd"
TIMEOUT_KEY = "controller.sync.timeout.seconds"
TIMEOUT_ENV = "ARGOCD_APPLICATION_CONTROLLER_SYNC_TIMEOUT"


def load(path):
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def render(path, *args):
    result = subprocess.run(
        ["kustomize", "build", str(path), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    if result.returncode:
        raise AssertionError(f"Render failed for {path}:\n{result.stderr}")
    return [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]


def policy(doc):
    spec = doc["spec"]
    if doc["kind"] == "ApplicationSet":
        spec = spec["template"]["spec"]
    return spec["syncPolicy"]


class SourceSyncRecoveryTests(unittest.TestCase):
    def test_deadline_is_a_command_parameter_not_a_polling_setting(self):
        values = load(ARGO / "values.yaml")
        self.assertEqual(values["configs"]["params"][TIMEOUT_KEY], "1800")
        self.assertNotIn(TIMEOUT_KEY, values["configs"]["cm"])
        for arg in values.get("controller", {}).get("extraArgs", []):
            self.assertFalse(arg.startswith("--sync-timeout"), "CLI overrides the ConfigMap")
        for entry in values.get("controller", {}).get("env", []):
            self.assertNotEqual(entry["name"], TIMEOUT_ENV, "Do not shadow the chart's env wiring")

    def test_bootstrap_seed_has_bounded_refreshing_retries(self):
        root = load(ARGO / "root.yaml")
        retry = policy(root)["retry"]
        self.assertIs(retry["refresh"], True)
        self.assertEqual(retry["limit"], 10)
        self.assertEqual(retry["backoff"], {"duration": "5s", "factor": 2, "maxDuration": "3m"})

    def test_root_remains_bootstrap_only(self):
        for path in (ARGO / "kustomization.yaml", ARGO / "apps/kustomization.yaml"):
            resources = load(path)["resources"]
            self.assertFalse(any(Path(item).name == "root.yaml" for item in resources))


class RenderedSyncRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing tools or broken renders must fail CI, not silently skip these checks.
        cls.entrypoints = render(ARGO / "apps")
        cls.controller_resources = render(ARGO, "--enable-helm")

    def test_all_entrypoints_and_generated_apps_refresh_retries(self):
        apps = [d for d in self.entrypoints if d["kind"] == "Application"]
        appsets = [d for d in self.entrypoints if d["kind"] == "ApplicationSet"]
        self.assertGreater(len(apps), 0)
        self.assertEqual(
            {d["metadata"]["name"] for d in appsets},
            {"infrastructure", "database", "monitoring", "my-apps"},
        )
        for doc in apps + appsets:
            with self.subTest(kind=doc["kind"], name=doc["metadata"]["name"]):
                retry = policy(doc)["retry"]
                self.assertIs(retry["refresh"], True)
                self.assertGreater(retry["limit"], 0)
                self.assertIn("maxDuration", retry["backoff"])

    def test_refresh_patch_preserves_existing_sync_safety_and_backoff(self):
        rendered = {(d["kind"], d["metadata"]["name"]): d for d in self.entrypoints}
        checked = 0
        for resource in load(ARGO / "apps/kustomization.yaml")["resources"]:
            with (ARGO / "apps" / resource).open(encoding="utf-8") as handle:
                for doc in yaml.safe_load_all(handle):
                    if not isinstance(doc, dict) or doc.get("kind") not in ("Application", "ApplicationSet"):
                        continue
                    key = (doc["kind"], doc["metadata"]["name"])
                    with self.subTest(resource=resource, name=key[1]):
                        before = deepcopy(policy(doc))
                        after = deepcopy(policy(rendered[key]))
                        before["retry"].pop("refresh", None)
                        after["retry"].pop("refresh", None)
                        self.assertEqual(after, before)
                    checked += 1
        self.assertGreater(checked, 0)

    def test_rendered_deadline_reaches_the_controller_and_rolls_its_pod(self):
        resources = {(d["kind"], d["metadata"]["name"]): d for d in self.controller_resources}
        params = resources[("ConfigMap", "argocd-cmd-params-cm")]
        self.assertEqual(params["data"][TIMEOUT_KEY], "1800")
        controller = resources[("StatefulSet", "argocd-application-controller")]
        template = controller["spec"]["template"]
        containers = template["spec"]["containers"]
        main = next(c for c in containers if c["name"] == "application-controller")
        refs = [e for e in main["env"] if e["name"] == TIMEOUT_ENV]
        self.assertEqual(len(refs), 1)
        self.assertNotIn("value", refs[0])
        ref = refs[0]["valueFrom"]["configMapKeyRef"]
        self.assertEqual((ref["name"], ref["key"]), ("argocd-cmd-params-cm", TIMEOUT_KEY))
        self.assertFalse(any(a.startswith("--sync-timeout") for a in main["args"]))
        self.assertRegex(template["metadata"]["annotations"]["checksum/cmd-params"], r"^[0-9a-f]{64}$")
        self.assertEqual(controller["spec"].get("updateStrategy", {}).get("type", "RollingUpdate"), "RollingUpdate")


if __name__ == "__main__":
    unittest.main()
