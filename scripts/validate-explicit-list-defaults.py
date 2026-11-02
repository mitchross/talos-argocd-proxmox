#!/usr/bin/env python3
"""Validate that API-server-defaulted fields inside CRD lists are spelled out in Git.

Argo CD 3.6 with `RespectIgnoreDifferences=true` swaps Git's whole CRD list for the
live one when an ignoreDifferences path points inside that list (CRD lists have no
patch merge key; argo-cd#26588). So we never ignore list paths, and instead write the
defaults in Git. Runs on the RENDERED stream so Helm and kustomize patches count.

    python3 scripts/validate-explicit-list-defaults.py /tmp/all-manifests.yaml

FAILS (exit 1) when
  * an HTTPRoute parentRef omits `group` or `kind`
  * an HTTPRoute backendRef omits `group`, `kind` or `weight`
  * a kopiur SnapshotPolicy source omits `sourcePathStrategy` or `readOnly`
"""
import re
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("pyyaml required: pip3 install pyyaml\n")
    sys.exit(2)

KINDS = ("HTTPRoute", "SnapshotPolicy")
KIND_RE = re.compile(r"^kind: (%s)\s*$" % "|".join(KINDS), re.M)
PARENT_FIELDS = ("group", "kind")
BACKEND_FIELDS = ("group", "kind", "weight")
SOURCE_FIELDS = ("sourcePathStrategy", "readOnly")


def load_docs(text):
    """Parse only the documents we check; one odd tag elsewhere must not break the run."""
    docs = []
    for chunk in re.split(r"^---\s*$", text, flags=re.M):
        if not KIND_RE.search(chunk):
            continue
        doc = yaml.load(chunk, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        if isinstance(doc, dict):
            docs.append(doc)
    return docs


def validate(docs):
    errors = []
    for doc in docs:
        kind = doc.get("kind")
        meta = doc.get("metadata") or {}
        who = f"{kind} {meta.get('namespace', '-')}/{meta.get('name')}"
        spec = doc.get("spec") or {}
        if kind == "HTTPRoute":
            for i, ref in enumerate(spec.get("parentRefs") or []):
                for f in PARENT_FIELDS:
                    if f not in ref:
                        errors.append(f"{who}: spec.parentRefs[{i}] omits `{f}`")
            for r, rule in enumerate(spec.get("rules") or []):
                for b, ref in enumerate(rule.get("backendRefs") or []):
                    for f in BACKEND_FIELDS:
                        if f not in ref:
                            errors.append(f"{who}: spec.rules[{r}].backendRefs[{b}] omits `{f}`")
        elif kind == "SnapshotPolicy" and "kopiur.home-operations.com" in str(doc.get("apiVersion")):
            for i, src in enumerate(spec.get("sources") or []):
                for f in SOURCE_FIELDS:
                    if f not in src:
                        errors.append(f"{who}: spec.sources[{i}] omits `{f}`")
    return errors


def main():
    if len(sys.argv) != 2:
        sys.stderr.write(f"usage: {sys.argv[0]} <rendered-manifests.yaml>\n")
        return 2
    with open(sys.argv[1]) as fh:
        docs = load_docs(fh.read())
    errors = validate(docs)
    print("== explicit list defaults ==")
    print(f"  checked {len(docs)} HTTPRoute/SnapshotPolicy objects")
    for e in errors:
        print(f"  FAIL {e}")
    if errors:
        print(
            f"\n{len(errors)} omitted default(s). Spell them out in Git: ArgoCD must not ignore CRD list paths "
            "(https://github.com/argoproj/argo-cd/issues/26588). HTTPRoute: parentRefs group "
            "`gateway.networking.k8s.io` + kind `Gateway`; backendRefs group `\"\"` + kind `Service` + weight `1`. "
            "SnapshotPolicy: sourcePathStrategy `PvcName` + readOnly `true` (my-apps/common/kopiur-backup)."
        )
        return 1
    print("\nValidation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
