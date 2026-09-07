"""Exercise the pinned API method without bootstrapping Django or a database."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "retention_patch", ROOT / "scripts/patch-replay-retention.py"
)
retention_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention_patch)
SOURCE = (ROOT / "tests/fixtures/retention_validator.py").read_text()


class APIError(Exception):
    def __init__(self, detail):
        super().__init__(detail)


class Denied(APIError):
    pass


class ReplayRetentionTests(unittest.TestCase):
    def validate(self, source, period, *, cloud=False, feature=None):
        periods = ["30d", "90d", "1y", "5y"]
        namespace = {
            "Team": object,
            "AvailableFeature": types.SimpleNamespace(SESSION_REPLAY_DATA_RETENTION="retention"),
            "parse_feature_to_entitlement": lambda f: f.get("entitlement") if f else None,
            "validate_retention_period": lambda p: p in periods,
            "VALID_RETENTION_PERIODS": periods,
            "retention_violates_entitlement": lambda p, e: periods.index(p) > periods.index(e),
            "exceptions": types.SimpleNamespace(
                APIException=APIError, ValidationError=APIError, PermissionDenied=Denied
            ),
        }
        cloud_module = types.ModuleType("posthog.cloud_utils")
        cloud_module.is_cloud = lambda: cloud
        team = types.SimpleNamespace(
            organization=types.SimpleNamespace(get_available_feature=lambda key: feature)
        )
        with patch.dict(sys.modules, {"posthog.cloud_utils": cloud_module}):
            exec(compile(source, "retention_validator.py", "exec"), namespace)
            namespace["TeamSerializer"]()._verify_update_session_recording_retention_period(team, period)

    def test_upstream_reproduces_missing_entitlement_error(self):
        with self.assertRaisesRegex(APIError, "Invalid retention entitlement"):
            self.validate(SOURCE, "30d")

    def test_self_hosted_missing_entitlement_accepts_thirty_days(self):
        self.validate(retention_patch.patch_source(SOURCE), "30d")

    def test_cloud_missing_entitlement_still_fails(self):
        with self.assertRaisesRegex(APIError, "Invalid retention entitlement"):
            self.validate(retention_patch.patch_source(SOURCE), "30d", cloud=True)

    def test_missing_entitlement_does_not_unlock_longer_retention(self):
        for period in ("90d", "1y", "5y", "legacy", "invalid"):
            with self.subTest(period=period), self.assertRaises(APIError):
                self.validate(retention_patch.patch_source(SOURCE), period)

    def test_malformed_existing_entitlement_still_fails(self):
        with self.assertRaises(APIError):
            self.validate(retention_patch.patch_source(SOURCE), "30d", feature={"entitlement": None})

    def test_valid_entitlement_keeps_original_allow_and_deny_behavior(self):
        source = retention_patch.patch_source(SOURCE)
        for cloud in (False, True):
            self.validate(source, "90d", cloud=cloud, feature={"entitlement": "90d"})
            with self.assertRaises(Denied):
                self.validate(source, "1y", cloud=cloud, feature={"entitlement": "90d"})

    def test_patch_is_idempotent(self):
        patched = retention_patch.patch_source(SOURCE)
        self.assertEqual(retention_patch.patch_source(patched), patched)

    def test_upstream_method_drift_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "changed"):
            retention_patch.patch_source(SOURCE.replace("Invalid retention entitlement.", "New behavior."))


if __name__ == "__main__":
    unittest.main()
