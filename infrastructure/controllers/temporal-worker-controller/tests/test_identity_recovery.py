"""Exercise recovery decisions and failures without calling either live API."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/recover-manager-identity.sh"


class IdentityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.env = os.environ | {
            "PATH": f"{self.directory}:{os.environ['PATH']}",
            "KUBERNETES_SERVICE_HOST": "kubernetes.test",
            "KUBERNETES_SERVICE_PORT_HTTPS": "443",
            "POD_NAMESPACE": "controller",
            "CONTROLLER_IDENTITY": "controller/manager",
            "TEMPORAL_ADDRESS": "temporal.test:7233",
            "TEMPORAL_NAMESPACE": "default",
            "CALLS": str(self.directory / "calls.jsonl"),
            "TIMEOUT_CALLS": str(self.directory / "timeouts"),
            "IDENTITIES": json.dumps({}),
        }
        self.executable("cat", '#!/bin/sh\nprintf "%s" "test-token"\n')
        self.executable("wget", '''#!/usr/bin/env python3
import os, sys
if os.environ.get("FAIL") == "namespace":
    sys.exit(7)
print('{"metadata": {"uid": "current-uid"}}')
''')
        self.executable("timeout", '''#!/bin/sh
test "$1 $2 $3" = "-k 5 30" || exit 90
printf '%s\\n' "$*" >> "$TIMEOUT_CALLS"
shift 3
exec /usr/bin/timeout -k 0.1 1 "$@"
''')
        self.executable("temporal", '''#!/usr/bin/env python3
import json, os, signal, sys, time
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as stream:
    stream.write(json.dumps(args) + "\\n")
action = "list" if "list" in args else "describe" if "describe" in args else "unset"
if os.environ.get("HANG") == action:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(0.01)
if os.environ.get("FAIL") == action:
    # Partial stdout must not let a failed command trigger a mutation.
    print('  "managerIdentity": "controller/manager/stale-uid"')
    sys.exit(7)
identities = json.loads(os.environ["IDENTITIES"])
if action == "list":
    for name in identities:
        print('  "name": "' + name + '",')
elif action == "describe":
    name = args[args.index("--name") + 1]
    print('  "managerIdentity": "' + identities[name] + '"')
''')

    def executable(self, name, content):
        path = self.directory / name
        path.write_text(content)
        path.chmod(0o755)

    def run_recovery(self, identities=None, **environment):
        self.env.update(environment)
        self.env["IDENTITIES"] = json.dumps(identities or {})
        return subprocess.run(
            ["/bin/sh", str(SCRIPT)], env=self.env,
            capture_output=True, text=True, timeout=5,
        )

    def calls(self):
        path = self.directory / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def assert_no_unset(self):
        self.assertFalse(any("unset" in call for call in self.calls()))

    def test_only_stale_owned_identity_is_cleared(self):
        result = self.run_recovery({
            "current": "controller/manager/current-uid",
            "stale": "controller/manager/old-uid",
            "foreign": "another-controller/old-uid",
            "empty": "",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        unsets = [call for call in self.calls() if "unset" in call]
        self.assertEqual(len(unsets), 1)
        self.assertEqual(unsets[0][unsets[0].index("--identity") + 1], "controller/manager/old-uid")
        self.assertEqual(unsets[0][unsets[0].index("--deployment-name") + 1], "stale")
        self.assertEqual(len((self.directory / "timeouts").read_text().splitlines()), 7)

    def test_no_deployments_is_successful_noop(self):
        result = self.run_recovery()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_no_unset()

    def test_namespace_error_stops_before_temporal(self):
        result = self.run_recovery(FAIL="namespace")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.calls(), [])

    def test_list_failure_is_not_hidden_by_parser(self):
        result = self.run_recovery(FAIL="list")
        self.assertEqual(result.returncode, 7)
        self.assert_no_unset()

    def test_describe_failure_does_not_use_partial_stdout(self):
        result = self.run_recovery({"stale": "controller/manager/old-uid"}, FAIL="describe")
        self.assertEqual(result.returncode, 7)
        self.assert_no_unset()

    def test_unset_failure_marks_run_failed(self):
        result = self.run_recovery({"stale": "controller/manager/old-uid"}, FAIL="unset")
        self.assertEqual(result.returncode, 7)
        self.assertNotIn("cleared stale", result.stdout)

    def test_stubborn_list_is_killed_and_marks_run_failed(self):
        result = self.run_recovery(HANG="list")
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_unset()

    def test_stubborn_describe_cannot_trigger_unset(self):
        result = self.run_recovery({"stale": "controller/manager/old-uid"}, HANG="describe")
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_unset()


if __name__ == "__main__":
    unittest.main()
