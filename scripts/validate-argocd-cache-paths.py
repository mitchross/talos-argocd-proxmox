#!/usr/bin/env python3
"""Validate rendered Argo cache hints, including the manually seeded root."""
import argparse
import posixpath
from pathlib import Path

import yaml

ANNOTATION = "argocd.argoproj.io/manifest-generate-paths"


def resolve_paths(source: str, annotation: str) -> list[str]:
    """Resolve directory hints using Argo's source-relative/repo-absolute rules."""
    return [
        posixpath.normpath(p.lstrip("/") if p.startswith("/") else posixpath.join(source, p))
        for p in annotation.split(";") if p
    ]


def covers(directory: str, dependency: str) -> bool:
    return directory == "." or dependency == directory or dependency.startswith(directory + "/")


def validate(documents: list[dict]) -> list[str]:
    errors = []
    checked = 0
    for obj in documents:
        kind = obj.get("kind")
        if kind not in ("Application", "ApplicationSet"):
            continue
        checked += 1
        name = obj["metadata"]["name"]
        app = obj["spec"]["template"] if kind == "ApplicationSet" else obj
        source = app.get("spec", {}).get("source", {}).get("path")
        if not source:
            # Chart-only Applications have no local Kustomize dependency graph.
            continue
        hint = app.get("metadata", {}).get("annotations", {}).get(ANNOTATION, "")
        if not hint:
            errors.append(f"{name}: missing cache hint")
            continue
        if "{{" in source:
            source = "my-apps/ai/example" if name == "my-apps" else f"{name}/example"
            hint = hint.replace("{{ .path.path }}", source)
        paths = resolve_paths(source, hint)
        if not any(covers(path, source) for path in paths):
            errors.append(f"{name}: {hint!r} does not cover source {source!r}; resolves to {paths}")
        if name == "my-apps" and not any(covers(path, "my-apps/common") for path in paths):
            errors.append(f"{name}: shared Components are outside cache hints {paths}")
        if any(path == ".." or path.startswith("../") for path in paths):
            errors.append(f"{name}: hint escapes the repository")
    if not checked:
        errors.append("No Application or ApplicationSet objects supplied")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        docs = [doc for path in args.manifests for doc in yaml.safe_load_all(path.read_text()) if doc]
        errors = validate(docs)
    except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError) as exc:
        print(f"ERROR: cannot validate manifests: {exc}")
        return 1
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("Argo cache hints cover application roots and shared Components.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
