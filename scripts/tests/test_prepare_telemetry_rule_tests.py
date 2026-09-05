"""Offline tests for preparing the inputs consumed by promtool."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "prepare-telemetry-rule-tests.py"
spec = importlib.util.spec_from_file_location("prepare_telemetry", SCRIPT)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PrepareTelemetryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name) / "source"
        self.output = Path(temporary.name) / "output/nested"
        (self.source / "tests").mkdir(parents=True)
        self.manifest = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusRule",
            "metadata": {"name": "example"},
            "spec": {"groups": [{"name": "example", "rules": [{"alert": "Down", "expr": "up == 0"}]}]},
        }
        self.rule_file = self.source / "collector-alerts.yaml"
        self.rule_file.write_text(yaml.safe_dump(self.manifest), encoding="utf-8")
        self.fixture_file = self.source / "tests/collector-alerts.test.yaml"
        self.fixture_file.write_bytes(b"rule_files:\n- collector.rules.yaml\ntests: []\n")

    def test_output_matches_previous_inline_script(self):
        prepare.prepare_tests(self.source, self.output)
        self.assertEqual(
            (self.output / "collector.rules.yaml").read_text(encoding="utf-8"),
            yaml.safe_dump(self.manifest["spec"]),
        )
        self.assertEqual(
            (self.output / "collector-alerts.test.yaml").read_bytes(),
            self.fixture_file.read_bytes(),
        )

    def test_repeat_run_updates_generated_rules(self):
        prepare.prepare_tests(self.source, self.output)
        self.manifest["spec"]["groups"][0]["rules"][0]["expr"] = "up == 1"
        self.rule_file.write_text(yaml.safe_dump(self.manifest), encoding="utf-8")
        prepare.prepare_tests(self.source, self.output)
        self.assertEqual(
            yaml.safe_load((self.output / "collector.rules.yaml").read_text(encoding="utf-8")),
            self.manifest["spec"],
        )

    def test_missing_or_empty_groups_fail_before_writing(self):
        for manifest in (None, [], {}, {"spec": {}}, {"spec": {"groups": []}}):
            with self.subTest(manifest=manifest):
                self.rule_file.write_text(yaml.safe_dump(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    prepare.prepare_tests(self.source, self.output)
                self.assertFalse(self.output.exists())

    def test_invalid_yaml_fails_before_writing(self):
        self.rule_file.write_text("spec: [", encoding="utf-8")
        with self.assertRaises(yaml.YAMLError):
            prepare.prepare_tests(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_fixture_fails_before_writing(self):
        self.fixture_file.unlink()
        with self.assertRaises(FileNotFoundError):
            prepare.prepare_tests(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_cli_returns_failure_when_inputs_are_missing(self):
        with patch.object(prepare, "SOURCE_DIR", self.source / "missing"), \
             patch("sys.argv", [str(SCRIPT), str(self.output)]), \
             patch("sys.stderr") as stderr:
            self.assertEqual(prepare.main(), 1)
        self.assertIn("ERROR:", "".join(call.args[0] for call in stderr.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
