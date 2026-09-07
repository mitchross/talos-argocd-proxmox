"""Offline schema-generation and resource-validation regressions."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft4Validator
import yaml

SCRIPT = Path(__file__).parents[1] / "generate-crd-schemas.py"
GROUP = "example.com"
MODULE_SPEC = importlib.util.spec_from_file_location("crd_schemas", SCRIPT)
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


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


OBJECT = {
    "type": "object",
    "properties": {"spec": {"type": "object", "properties": {"size": {"type": "string"}}}},
}


class GenerateCrdSchemasTest(unittest.TestCase):
    def generate(self, *docs, extra=()):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "rendered.yaml"
        path.write_text(yaml.safe_dump_all(docs), encoding="utf-8")
        out = Path(directory.name) / "schemas"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(path), str(out), *extra],
            capture_output=True, text=True, check=False,
        )
        return result, out

    def validator(self, schema):
        result, out = self.generate(crd(schema))
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = json.loads((out / GROUP / "widget_v1.json").read_text())
        Draft4Validator.check_schema(generated)
        return Draft4Validator(generated)

    def test_prunes_unknown_fields(self):
        validator = self.validator(OBJECT)
        self.assertTrue(validator.is_valid({"spec": {"size": "small"}}))
        self.assertFalse(validator.is_valid({"spec": {"szie": "small"}}))
        self.assertFalse(validator.is_valid({"spec": {"size": 3}}))
        self.assertFalse(validator.is_valid({"typo": True}))

    def test_preserve_unknown_subtree_stays_open(self):
        body = deepcopy(OBJECT)
        body["properties"]["job"] = {
            "type": "object", "x-kubernetes-preserve-unknown-fields": True,
        }
        validator = self.validator(body)
        self.assertTrue(validator.is_valid({"job": {"arbitrary": {"nested": True}}}))
        self.assertFalse(validator.is_valid({"job": "not-an-object"}))

    def test_preserved_parent_still_checks_declared_children(self):
        body = deepcopy(OBJECT)
        body["x-kubernetes-preserve-unknown-fields"] = True
        validator = self.validator(body)
        self.assertTrue(validator.is_valid({"arbitrary": True, "spec": {"size": "small"}}))
        self.assertFalse(validator.is_valid({"arbitrary": True, "spec": {"szie": "small"}}))

    def test_preserved_map_checks_values(self):
        body = {
            "type": "object", "x-kubernetes-preserve-unknown-fields": True,
            "additionalProperties": deepcopy(OBJECT["properties"]["spec"]),
        }
        validator = self.validator({"type": "object", "properties": {"entries": body}})
        self.assertTrue(validator.is_valid({"entries": {"anything": {"size": "small"}}}))
        self.assertFalse(validator.is_valid({"entries": {"anything": {"szie": "small"}}}))

    def test_root_preservation_without_declared_properties(self):
        validator = self.validator({"type": "object", "x-kubernetes-preserve-unknown-fields": True})
        self.assertTrue(validator.is_valid({"anything": {"nested": 1}}))

    def test_map_value_schema_is_not_closed(self):
        body = {
            "type": "object",
            "properties": {"labels": {"type": "object", "additionalProperties": {"type": "string"}}},
        }
        validator = self.validator(body)
        self.assertTrue(validator.is_valid({"labels": {"arbitrary": "value"}}))
        self.assertFalse(validator.is_valid({"labels": {"arbitrary": 3}}))

    def test_metadata_left_open(self):
        body = {"type": "object", "properties": {"metadata": {"type": "object", "properties": {}}}}
        validator = self.validator(body)
        self.assertTrue(validator.is_valid({"metadata": {"labels": {"app": "test"}, "annotations": {"x": "y"}}}))
        self.assertFalse(validator.is_valid({"metadata": "wrong-type"}))

    def test_embedded_resource_keeps_implicit_fields(self):
        embedded = deepcopy(OBJECT)
        embedded["x-kubernetes-embedded-resource"] = True
        validator = self.validator({"type": "object", "properties": {"template": embedded}})
        resource = {"apiVersion": "example.com/v1", "kind": "Widget", "metadata": {"name": "x"}, "spec": {"size": "small"}}
        self.assertTrue(validator.is_valid({"template": resource}))
        resource["spec"]["szie"] = "small"
        self.assertFalse(validator.is_valid({"template": resource}))

    def test_composition_does_not_close_partial_branches(self):
        for keyword in ("allOf", "anyOf", "oneOf", "not"):
            with self.subTest(keyword=keyword):
                body = deepcopy(OBJECT)
                spec = body["properties"]["spec"]
                spec["properties"]["other"] = {"type": "string"}
                constraint = {"properties": {"size": {"enum": ["bad" if keyword == "not" else "good"]}}}
                spec[keyword] = constraint if keyword == "not" else [constraint]
                validator = self.validator(body)
                self.assertTrue(validator.is_valid({"spec": {"size": "good", "other": "allowed"}}))
                self.assertFalse(validator.is_valid({"spec": {"size": "bad", "other": "allowed"}}))
                self.assertFalse(validator.is_valid({"spec": {"size": "good", "typo": "rejected"}}))

    def test_nested_composition_does_not_close_children(self):
        body = deepcopy(OBJECT)
        spec = body["properties"]["spec"]
        spec["properties"]["other"] = {"type": "string"}
        body["allOf"] = [{"properties": {"spec": {"properties": {"size": {"minLength": 2}}}}}]
        validator = self.validator(body)
        self.assertTrue(validator.is_valid({"spec": {"size": "ok", "other": "allowed"}}))
        self.assertFalse(validator.is_valid({"spec": {"size": "x", "other": "allowed"}}))
        self.assertFalse(validator.is_valid({"spec": {"size": "ok", "typo": "rejected"}}))

    def test_array_items_are_strict(self):
        body = {"type": "object", "properties": {"entries": {"type": "array", "items": deepcopy(OBJECT["properties"]["spec"])}}}
        validator = self.validator(body)
        self.assertTrue(validator.is_valid({"entries": [{"size": "ok"}]}))
        self.assertFalse(validator.is_valid({"entries": [{"szie": "bad"}]}))

    def test_nullable_types(self):
        for field, valid, invalid in (
            ({"type": "string", "minLength": 2}, "ok", 5),
            ({"type": "integer", "minimum": 1}, 2, "bad"),
            (deepcopy(OBJECT["properties"]["spec"]), {"size": "ok"}, {"szie": "bad"}),
            ({"type": "array", "items": {"type": "string"}}, ["ok"], [5]),
        ):
            with self.subTest(field=field):
                field["nullable"] = True
                validator = self.validator({"type": "object", "properties": {"value": field}, "required": ["value"]})
                self.assertTrue(validator.is_valid({"value": None}))
                self.assertTrue(validator.is_valid({"value": valid}))
                self.assertFalse(validator.is_valid({"value": invalid}))
                self.assertFalse(validator.is_valid({}))

    def test_int_or_string(self):
        for field in (
            {"x-kubernetes-int-or-string": True},
            {"format": "int-or-string", "type": "string"},
            {"x-kubernetes-int-or-string": True, "anyOf": [{"type": "integer"}, {"type": "string"}]},
            {"x-kubernetes-int-or-string": True, "allOf": [{"anyOf": [{"type": "integer"}, {"type": "string"}]}]},
        ):
            with self.subTest(field=field):
                validator = self.validator({"type": "object", "properties": {"port": field}})
                for value in (8080, "http"):
                    self.assertTrue(validator.is_valid({"port": value}))
                for value in (True, 1.5, {}, [], None):
                    self.assertFalse(validator.is_valid({"port": value}))

    def test_nullable_int_or_string_with_composition(self):
        field = {"x-kubernetes-int-or-string": True, "nullable": True, "anyOf": [{"type": "integer"}, {"type": "string"}]}
        validator = self.validator({"type": "object", "properties": {"port": field}})
        for value in (None, 8080, "http"):
            self.assertTrue(validator.is_valid({"port": value}))
        self.assertFalse(validator.is_valid({"port": True}))

    def test_nullable_does_not_bypass_enum(self):
        field = {"type": "string", "nullable": True, "enum": ["allowed"]}
        validator = self.validator({"type": "object", "properties": {"value": field}})
        self.assertFalse(validator.is_valid({"value": None}))
        self.assertTrue(validator.is_valid({"value": "allowed"}))

    def test_conversion_does_not_mutate_input(self):
        original = deepcopy(OBJECT)
        MODULE.convert(OBJECT)
        self.assertEqual(OBJECT, original)

    def test_canary_pair_differs_only_in_timeout_placement(self):
        fixtures = Path(__file__).parent / "fixtures"
        broken = yaml.safe_load((fixtures / "crd-schema-canary.yaml").read_text())
        fixed = yaml.safe_load((fixtures / "crd-schema-valid.yaml").read_text())
        hook = broken["spec"]["hooks"]["beforeSnapshot"][0]
        hook["workloadExec"]["timeout"] = hook.pop("timeout")
        self.assertEqual(broken, fixed)

    def test_unserved_version_skipped(self):
        doc = crd(OBJECT)
        doc["spec"]["versions"][0]["served"] = False
        result, out = self.generate(doc, extra=["--min-schemas", "0"])
        self.assertEqual(result.returncode, 0)
        self.assertFalse((out / GROUP).exists())

    def test_min_schemas_guard_fails_loudly(self):
        result, _ = self.generate({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "x"}}, extra=["--min-schemas", "1"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected at least", result.stderr)

    def test_value_tag_in_crd_enum_parses(self):
        body = {"type": "object", "properties": {"op": {"type": "string", "enum": ["=", "!="]}}}
        stream = yaml.safe_dump_all([crd(body)]).replace("- '='", "- =")
        parsed = list(MODULE.iter_crds(stream))
        self.assertEqual(parsed[0]["spec"]["versions"][0]["schema"]["openAPIV3Schema"], body)


if __name__ == "__main__":
    unittest.main()
