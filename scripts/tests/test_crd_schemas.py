"""Offline regression cases; these fixtures are not deployable applications."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

import yaml

SCRIPT = Path(__file__).parents[1] / "generate-crd-schemas.py"
GROUP = "example.com"


def crd(schema, kind="Widget", version="v1"):
    return {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": f"{kind.lower()}s.{GROUP}"},
        "spec": {
            "group": GROUP,
            "names": {"kind": kind},
            "versions": [{"name": version, "served": True, "schema": {"openAPIV3Schema": schema}}],
        },
    }


def generate(*docs, extra=()):
    directory = tempfile.mkdtemp()
    path = Path(directory) / "rendered.yaml"
    path.write_text(yaml.safe_dump_all(docs))
    out = Path(directory) / "schemas"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), str(out), *extra], capture_output=True, text=True
    )
    return result, out


OBJECT = {
    "type": "object",
    "properties": {"spec": {"type": "object", "properties": {"size": {"type": "string"}}}},
}


class GenerateCrdSchemasTest(unittest.TestCase):
    def load(self, out, kind="widget", version="v1"):
        return json.loads((out / GROUP / f"{kind}_{version}.json").read_text())

    def test_prunes_unknown_fields(self):
        """The point of the tool: a CRD lists fields but never forbids others."""
        _, out = generate(crd(OBJECT))
        schema = self.load(out)
        self.assertIs(schema["properties"]["spec"]["additionalProperties"], False)

    def test_preserve_unknown_subtree_stays_open(self):
        """Where the API server stops pruning (embedded PodSpec/JobSpec), so do we."""
        body = {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "object",
                    "properties": {"job": {"type": "object", "x-kubernetes-preserve-unknown-fields": True}},
                }
            },
        }
        _, out = generate(crd(body))
        job = self.load(out)["properties"]["spec"]["properties"]["job"]
        self.assertNotIn("additionalProperties", job)

    def test_map_value_schema_is_not_closed(self):
        """map[string]string carries additionalProperties as a schema, not a bool."""
        body = {
            "type": "object",
            "properties": {"labels": {"type": "object", "additionalProperties": {"type": "string"}}},
        }
        _, out = generate(crd(body))
        labels = self.load(out)["properties"]["labels"]
        self.assertEqual(labels["additionalProperties"], {"type": "string"})

    def test_metadata_left_open(self):
        """A CRD that narrows metadata must not make us reject labels/annotations."""
        body = {"type": "object", "properties": {"metadata": {"type": "object", "properties": {}}}}
        _, out = generate(crd(body))
        self.assertTrue(self.load(out)["properties"]["metadata"]["x-kubernetes-preserve-unknown-fields"])

    def test_unserved_version_skipped(self):
        doc = crd(OBJECT)
        doc["spec"]["versions"][0]["served"] = False
        result, out = generate(doc, extra=["--min-schemas", "0"])
        self.assertEqual(result.returncode, 0)
        self.assertFalse((out / GROUP).exists())

    def test_min_schemas_guard_fails_loudly(self):
        """Without this the check rots silently: no CRDs found, nothing validated."""
        result, _ = generate({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "x"}},
                             extra=["--min-schemas", "1"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected at least", result.stderr)

    def test_value_tag_in_crd_enum_parses(self):
        """A bare `=` in an enum is the YAML value tag; SafeLoader rejects it raw."""
        body = {"type": "object", "properties": {"op": {"type": "string", "enum": ["=", "!="]}}}
        directory = tempfile.mkdtemp()
        path = Path(directory) / "rendered.yaml"
        path.write_text(yaml.safe_dump_all([crd(body)]).replace("- '='", "- ="))
        out = Path(directory) / "schemas"
        result = subprocess.run([sys.executable, str(SCRIPT), str(path), str(out)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
