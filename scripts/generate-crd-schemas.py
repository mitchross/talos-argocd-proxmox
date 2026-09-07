#!/usr/bin/env python3
"""Convert rendered CustomResourceDefinitions into kubeconform JSON schemas.

kubeconform runs with -ignore-missing-schemas and sources CRD schemas from the
datree CRDs-catalog, which does not carry niche charts (kopiur among them). Every
such CR was therefore unvalidated in CI: a field name typo only failed later, at
the API server, as an ArgoCD sync error. This closes that gap using the CRDs the
repo already renders, so the schemas always match the chart version in git.

    python3 scripts/generate-crd-schemas.py /tmp/all-manifests.yaml /tmp/crd-schemas

Writes <out>/<group>/<kind lowercased>_<version>.json, the layout kubeconform's
'{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' template resolves.

THE CONVERSION IS THE WHOLE POINT: a CRD's openAPIV3Schema lists the fields that
exist but never says "and nothing else". Rejecting unknown fields is structural
pruning, an API server behaviour that is absent from the schema document. Handing
kubeconform a raw extraction produces a check that validates field *types* and
happily passes a misplaced field -- the exact bug class this exists to catch. So
additionalProperties:false is injected recursively, except under
x-kubernetes-preserve-unknown-fields, where the API server also stops pruning.

Limits worth knowing: this is a strict subset of `kubectl apply --dry-run=server`.
Admission webhooks and x-kubernetes-validations CEL rules are not evaluated, so a
CR can pass here and still be rejected by the cluster.
"""

import json
import pathlib
import sys

import yaml

# A free-form object (no properties, no declared map value type) must stay open;
# forcing additionalProperties:false there would reject all of its content.
def _prune(node):
    if isinstance(node, list):
        for item in node:
            _prune(item)
        return
    if not isinstance(node, dict):
        return

    # Where the API server stops pruning, so do we.
    if node.get("x-kubernetes-preserve-unknown-fields"):
        return

    props = node.get("properties")
    if isinstance(props, dict):
        node.setdefault("additionalProperties", False)
        for sub in props.values():
            _prune(sub)

    # Map value schemas (map[string]T) arrive here as a dict, not a bool.
    extra = node.get("additionalProperties")
    if isinstance(extra, dict):
        _prune(extra)

    for key in ("items", "not"):
        if key in node:
            _prune(node[key])
    for key in ("allOf", "anyOf", "oneOf"):
        if key in node:
            _prune(node[key])


def convert(schema):
    """One CRD version's openAPIV3Schema -> a whole-document kubeconform schema."""
    doc = json.loads(json.dumps(schema))  # never mutate the caller's copy
    _prune(doc)
    props = doc.setdefault("properties", {})
    props.setdefault("apiVersion", {"type": "string"})
    props.setdefault("kind", {"type": "string"})
    # ObjectMeta is validated by the API server, not by the CRD's own schema.
    props["metadata"] = {"type": "object", "x-kubernetes-preserve-unknown-fields": True}
    doc.setdefault("additionalProperties", False)
    return doc


def iter_crds(stream):
    # A bare `=` in a CRD enum (Prometheus Operator matchType) parses as the
    # rarely-used value tag, which SafeLoader rejects. Same shim as
    # validate-kopiur-coverage.py.
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

    # Without this the check rots silently: a moved chart path yields zero
    # schemas, kubeconform validates nothing, and CI stays green.
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
