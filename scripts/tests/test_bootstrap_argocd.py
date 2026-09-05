import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
STUB = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["BOOTSTRAP_TEST_CALLS"], "a") as f:
    f.write(json.dumps([name, *args]) + "\\n")
if name == "helm":
    print(os.environ.get("BOOTSTRAP_TEST_HELM_ERROR", "installed"))
    sys.exit(int(os.environ.get("BOOTSTRAP_TEST_HELM_EXIT", "0")))
if name == "cilium":
    sys.exit(int(os.environ.get("BOOTSTRAP_TEST_CILIUM_EXIT", "0")))
if name == "openssl":
    print("test-only-random-auth")
if name == "kubectl":
    if args[:3] == ["get", "ds", "cilium"]:
        print("quay.io/cilium/cilium:v" + os.environ["BOOTSTRAP_TEST_CILIUM_VERSION"])
    elif args[:3] == ["get", "secret", "argocd-redis"]:
        sys.exit(0 if os.environ.get("BOOTSTRAP_TEST_REDIS_EXISTS") else 1)
    elif args[:2] == ["wait", "--for=condition=Available"]:
        sys.exit(int(os.environ.get("BOOTSTRAP_TEST_SERVER_EXIT", "0")))
'''


class BootstrapTests(unittest.TestCase):
    def run_bootstrap(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for command in ["helm", "kubectl", "cilium", "openssl"]:
                path = folder / command
                path.write_text(STUB)
                path.chmod(0o755)
            calls_path = folder / "calls.jsonl"
            version = re.search(r"version:\s*[\"']?([\d.]+)", (
                ROOT / "infrastructure/networking/cilium/kustomization.yaml"
            ).read_text()).group(1)
            env = dict(os.environ, PATH=f"{folder}:{os.environ['PATH']}",
                       BOOTSTRAP_TEST_CALLS=str(calls_path),
                       BOOTSTRAP_TEST_CILIUM_VERSION=version, **overrides)
            result = subprocess.run(["bash", str(ROOT / "scripts/bootstrap-argocd.sh")],
                                    env=env, text=True, capture_output=True, timeout=15)
            calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
            return result, calls

    @staticmethod
    def root_applied(calls):
        return any(call[:2] == ["kubectl", "apply"] and
                   any(arg.endswith("/argocd/root.yaml") for arg in call) for call in calls)

    def test_fresh_install_preserves_configured_admin_credential(self):
        result, calls = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.root_applied(calls))
        helm = next(call for call in calls if call[0] == "helm")
        self.assertTrue(any(arg.startswith("configs.secret.argocdServerAdminPassword=") for arg in helm))
        self.assertIn("Admin password is pre-configured", result.stdout)

    def test_successful_rerun_preserves_redis_secret(self):
        result, calls = self.run_bootstrap(BOOTSTRAP_TEST_REDIS_EXISTS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call[:3] == ["kubectl", "create", "secret"] for call in calls))

    def test_any_helm_failure_stops_even_if_old_server_is_available(self):
        for error in ["chart repository unavailable", "conflict on argocd-secret admin.passwordMtime"]:
            with self.subTest(error=error):
                result, calls = self.run_bootstrap(BOOTSTRAP_TEST_HELM_EXIT="42",
                                                  BOOTSTRAP_TEST_HELM_ERROR=error)
                self.assertEqual(result.returncode, 42)
                self.assertFalse(self.root_applied(calls))
                self.assertNotIn("bootstrap complete", result.stdout)

    def test_server_readiness_failure_does_not_apply_root(self):
        result, calls = self.run_bootstrap(BOOTSTRAP_TEST_SERVER_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.root_applied(calls))

    def test_unhealthy_cni_stops_before_installation(self):
        result, calls = self.run_bootstrap(BOOTSTRAP_TEST_CILIUM_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[0] == "helm" for call in calls))


if __name__ == "__main__":
    unittest.main()
