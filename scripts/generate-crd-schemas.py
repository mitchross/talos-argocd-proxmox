#!/usr/bin/env python3
"""Convert rendered CRDs into strict kubeconform JSON schemas.

Usage: generate-crd-schemas.py MANIFESTS OUT_DIR [--min-schemas N]
Writes <out>/<group>/<kind lowercased>_<version>.json.

This is an offline field/type check, not an API-server dry run. Admission,
CEL, defaulting and full ObjectMeta validation still require the cluster.
"""

import copy
import json
import pathlib
import sys

import yaml


def _resource_fields(node: dict) -> None:
    props = node.setdefault("properties", {})
    props.setdefault("apiVersion", {"type": "string"})
    props.setdefault("kind", {"type": "string"})
    # CRD schemas do not describe the full ObjectMeta contract.
    props["metadata"] = {"type": "object", "x-kubernetes-preserve-unknown-fields": True}


def _convert_node(node: object, *, structural: bool = True) -> None:
    if isinstance(node, list):
        for item in node:
            _convert_node(item, structural=structural)
        return
    if not isinstance(node, dict):
        return

    if structural and node.get("x-kubernetes-embedded-resource"):
        _resource_fields(node)

    props = node.get("properties")
    if isinstance(props, dict):
        # Logical branches constrain fields; only the structural schema closes them.
        if structural and not node.get("x-kubernetes-preserve-unknown-fields"):
            node.setdefault("additionalProperties", False)
        # Preservation applies here, not to explicitly declared child schemas.
        for sub in props.values():
            _convert_node(sub, structural=structural)

    extra = node.get("additionalProperties")
    if isinstance(extra, dict):
        _convert_node(extra, structural=structural)
    if "items" in node:
        _convert_node(node["items"], structural=structural)
    for key in ("allOf", "anyOf", "oneOf", "not"):
        if key in node:
            _convert_node(node[key], structural=False)

    if node.get("x-kubernetes-int-or-string") or node.get("format") == "int-or-string":
        node["type"] = ["integer", "string"]
        if node.get("format") == "int-or-string":
            del node["format"]

    if node.pop("nullable", False):
        value_type = node.get("type")
        if isinstance(value_type, str):
            node["type"] = [value_type, "null"]
        elif isinstance(value_type, list) and "null" not in value_type:
            node["type"] = [*value_type, "null"]
        # Kubernetes checks nullable nulls against type/enum, not logical branches.
        constraints = {key: node.pop(key) for key in ("allOf", "anyOf", "oneOf", "not") if key in node}
        if constraints:
            node["allOf"] = [{"anyOf": [{"type": "null"}, constraints]}]


def convert(schema: dict) -> dict:
    """Convert one CRD version without mutating its source schema."""
    doc = copy.deepcopy(schema)
    _resource_fields(doc)
    _convert_node(doc)
    return doc


def iter_crds(stream):
    # Prometheus Operator's bare '=' enum value uses PyYAML's value tag.
    yaml.SafeLoader.add_constructor(
        "tag:yaml.org,2002:value", lambda loader, node: loader.construct_scalar(node)
    )
    for doc in yaml.safe_load_all(stream):
        if isinstance(doc, dict) and doc.get("kind") == "CustomResourceDefinition":
            yield doc


def generate(manifests_path, out_dir):
    out_dir = pathlib.Path(out_dir)
    with open(manifests_path, encoding="utf-8") as handle:
        crds = list(iter_crds(handle))

    written = []
    for crd in crds:
        spec = crd.get("spec", {})
        group = spec.get("group")
        kind = spec.get("names", {}).get("kind")
        if not group or not kind:
            continue
        for version in spec.get("versions", []):
            schema = version.get("schema", {}).get("openAPIV3Schema")
            if not schema or not version.get("served", True):
                continue
            target = out_dir / group / f"{kind.lower()}_{version['name']}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(convert(schema)), encoding="utf-8")
            written.append(target)
    return written


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    manifests, out_dir = argv[1], argv[2]
    minimum = 1
    if "--min-schemas" in argv:
        minimum = int(argv[argv.index("--min-schemas") + 1])

    written = generate(manifests, out_dir)
    print(f"Generated {len(written)} CRD schemas into {out_dir}")

    # Missing CRD-bearing charts must not silently remove all local validation.
    if len(written) < minimum:
        print(
            f"ERROR: expected at least {minimum} CRD schemas, got {len(written)}. "
            "The render stream is probably missing its CRD-bearing charts.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
