#!/usr/bin/env python3
"""Validate VPA policy safety against the repository's aggregated render."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


class ManifestLoader(yaml.SafeLoader):
    """Safe loader with Helm's bare `=` scalar accepted."""


ManifestLoader.add_constructor(
    "tag:yaml.org,2002:value",
    lambda loader, node: loader.construct_scalar(node),
)

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "Prometheus", "Alertmanager"}
ACTIVE_MODE = "InPlaceOrRecreate"
ALLOWED_MODES = {ACTIVE_MODE, "Off"}


def identity(obj: dict[str, Any]) -> tuple[str, str, str, str]:
    meta = obj.get("metadata") or {}
    return (
        str(obj.get("apiVersion", "")),
        str(obj.get("kind", "")),
        str(meta.get("namespace", "")),
        str(meta.get("name", "")),
    )


def target_identity(vpa: dict[str, Any]) -> tuple[str, str, str, str]:
    ref = vpa["spec"]["targetRef"]
    return (
        str(ref.get("apiVersion", "")),
        str(ref.get("kind", "")),
        str(vpa.get("metadata", {}).get("namespace", "")),
        str(ref.get("name", "")),
    )


def label(key: tuple[str, str, str, str]) -> str:
    api, kind, namespace, name = key
    return f"{api} {kind} {namespace or '<default>'}/{name}"


def matches_exception(
    key: tuple[str, str, str, str], entry: dict[str, Any]
) -> bool:
    api, kind, namespace, name = key
    if (
        entry.get("apiVersion") != api
        or entry.get("kind") != kind
        # Some Helm charts rely on the Argo destination namespace and omit it
        # from rendered workload metadata. In that case name/kind/API remain
        # unique and the reviewed exception still applies.
        or (namespace and entry.get("namespace", "") != namespace)
    ):
        return False
    if "name" in entry:
        return entry["name"] == name
    return bool(re.search(str(entry.get("namePattern", r"$^")), name))


def target_exists(
    key: tuple[str, str, str, str],
    objects: dict[tuple[str, str, str, str], dict[str, Any]],
) -> bool:
    if key in objects:
        return True
    # A few Helm charts omit metadata.namespace and rely on the Argo
    # destination namespace. Only accept that fallback when name/kind/API are
    # unique in the render.
    api, kind, _namespace, name = key
    candidates = [
        candidate
        for candidate in objects
        if candidate[0] == api and candidate[1] == kind and candidate[3] == name
    ]
    return len(candidates) == 1


def cpu_controlled(vpa: dict[str, Any]) -> bool:
    policies = (
        vpa.get("spec", {})
        .get("resourcePolicy", {})
        .get("containerPolicies", [])
    )
    for policy in policies:
        if policy.get("mode") == "Off":
            continue
        resources = policy.get("controlledResources")
        if resources is None or "cpu" in resources:
            return True
    return False


def hpa_cpu_targets(
    documents: list[dict[str, Any]],
) -> set[tuple[str, str, str, str]]:
    result: set[tuple[str, str, str, str]] = set()
    for obj in documents:
        kind = obj.get("kind")
        meta = obj.get("metadata") or {}
        spec = obj.get("spec") or {}
        if kind == "HorizontalPodAutoscaler":
            has_cpu_utilization = any(
                metric.get("type") == "Resource"
                and metric.get("resource", {}).get("name") == "cpu"
                and metric.get("resource", {})
                .get("target", {})
                .get("type") == "Utilization"
                for metric in spec.get("metrics", [])
            )
            if has_cpu_utilization:
                ref = spec.get("scaleTargetRef") or {}
                result.add(
                    (
                        ref.get("apiVersion", "apps/v1"),
                        ref.get("kind", "Deployment"),
                        meta.get("namespace", ""),
                        ref.get("name", ""),
                    )
                )
        elif kind == "ScaledObject":
            has_cpu_utilization = any(
                trigger.get("type") == "cpu"
                and trigger.get("metricType", "Utilization") == "Utilization"
                for trigger in spec.get("triggers", [])
            )
            if has_cpu_utilization:
                ref = spec.get("scaleTargetRef") or {}
                result.add(
                    (
                        ref.get("apiVersion", "apps/v1"),
                        ref.get("kind", "Deployment"),
                        meta.get("namespace", ""),
                        ref.get("name", ""),
                    )
                )
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} <rendered-manifests.yaml>")
        return 2

    manifest_path = Path(sys.argv[1])
    exemptions_path = Path(__file__).with_name("vpa-exemptions.yaml")
    exemptions = yaml.safe_load(exemptions_path.read_text()) or {}
    coverage_exemptions = exemptions.get("coverageExemptions", [])
    generated_targets = exemptions.get("generatedTargets", [])
    namespace_exemptions = exemptions.get("namespaceExemptions", [])
    workload_exemptions = exemptions.get("workloadExemptions", [])

    for category, entries in exemptions.items():
        for entry in entries:
            if not entry.get("reason"):
                print(f"ERROR: {category} entry is missing a reason: {entry}")
                return 1

    documents = [
        obj
        for obj in yaml.load_all(manifest_path.read_text(), Loader=ManifestLoader)
        if isinstance(obj, dict) and obj.get("kind")
    ]
    by_identity: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    occurrences: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for obj in documents:
        key = identity(obj)
        occurrences[key] += 1
        by_identity.setdefault(key, obj)

    vpas = [obj for obj in documents if obj.get("kind") == "VerticalPodAutoscaler"]
    # The aggregate render includes some bases more than once. Deduplicate the
    # same VPA object identity while still detecting two VPAs on one target.
    unique_vpas = {identity(vpa): vpa for vpa in vpas}
    target_to_vpas: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    errors: list[str] = []
    warnings: list[str] = []

    for vpa in unique_vpas.values():
        vpa_key = identity(vpa)
        target = target_identity(vpa)
        target_to_vpas[target].append(vpa)
        spec = vpa.get("spec") or {}
        policy = spec.get("updatePolicy") or {}
        mode = policy.get("updateMode")

        if mode not in ALLOWED_MODES:
            errors.append(f"{label(vpa_key)} uses unsupported updateMode={mode!r}")
        if mode == ACTIVE_MODE and policy.get("minReplicas") != 1:
            errors.append(f"{label(vpa_key)} must set minReplicas: 1")

        for container_policy in (
            spec.get("resourcePolicy", {}).get("containerPolicies", [])
        ):
            if container_policy.get("mode") == "Off":
                continue
            if container_policy.get("controlledValues") != "RequestsOnly":
                errors.append(
                    f"{label(vpa_key)} container "
                    f"{container_policy.get('containerName')} must use RequestsOnly"
                )

        generated = any(matches_exception(target, entry) for entry in generated_targets)
        if not generated and not target_exists(target, by_identity):
            errors.append(f"{label(vpa_key)} target is absent from render: {label(target)}")

        workload = by_identity.get(target)
        if workload:
            containers = (
                workload.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers", [])
            )
            wildcard = any(
                item.get("containerName") == "*"
                for item in spec.get("resourcePolicy", {}).get(
                    "containerPolicies", []
                )
            )
            if wildcard and len(containers) > 1:
                warnings.append(
                    f"{label(vpa_key)} uses a wildcard per-container ceiling "
                    f"for {len(containers)} containers"
                )

    for target, target_vpas in target_to_vpas.items():
        if len(target_vpas) > 1:
            names = ", ".join(label(identity(vpa)) for vpa in target_vpas)
            errors.append(f"multiple VPAs target {label(target)}: {names}")

    for target in hpa_cpu_targets(documents):
        for vpa in target_to_vpas.get(target, []):
            if cpu_controlled(vpa):
                errors.append(
                    f"{label(identity(vpa))} controls CPU while an HPA/ScaledObject "
                    f"uses CPU utilization on {label(target)}"
                )

    workloads = {
        key: obj
        for key, obj in by_identity.items()
        if key[1] in WORKLOAD_KINDS
        and key[2] not in {"kube-system", "kube-public", "kube-node-lease"}
    }
    covered = set(target_to_vpas)
    covered_without_namespace = {
        (api, kind, name) for api, kind, _namespace, name in covered
    }
    excluded_namespaces = {
        entry["namespace"] for entry in namespace_exemptions
    }
    for key, workload in sorted(workloads.items()):
        replicas = workload.get("spec", {}).get("replicas", 1)
        if replicas == 0:
            continue
        if key in covered or (key[0], key[1], key[3]) in covered_without_namespace:
            continue
        if key[2] in excluded_namespaces:
            continue
        if any(matches_exception(key, entry) for entry in coverage_exemptions):
            continue
        if any(matches_exception(key, entry) for entry in workload_exemptions):
            continue
        warnings.append(f"{label(key)} has no VPA and no reviewed exemption")

    # Exact exemptions should not silently outlive their workload.
    for entry in coverage_exemptions:
        if "name" not in entry:
            continue
        key = (
            entry["apiVersion"],
            entry["kind"],
            entry.get("namespace", ""),
            entry["name"],
        )
        if not target_exists(key, by_identity):
            errors.append(f"stale VPA coverage exemption: {label(key)}")

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    print(
        f"Validated {len(unique_vpas)} VPA objects and "
        f"{len(target_to_vpas)} unique targets; "
        f"{len(errors)} error(s), {len(warnings)} warning(s)."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
