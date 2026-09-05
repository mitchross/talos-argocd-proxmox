#!/usr/bin/env python3
"""Check Cilium scrape discovery and exporter resources in rendered manifests."""
import argparse
from pathlib import Path

import yaml

MONITORS = {
    "cilium-metrics": "cilium-agent",
    "cilium-operator-metrics": "cilium-operator",
    "cilium-envoy-metrics": "cilium-envoy",
}
ARGO_MONITORS = {
    "argocd-application-controller", "argocd-applicationset-controller",
    "argocd-repo-server", "argocd-server",
}


def validate(objects):
    index = {(o["kind"], o["metadata"].get("namespace", "default"), o["metadata"]["name"]): o
             for o in objects}
    errors = []
    for monitor_name, service_name in MONITORS.items():
        monitor = index.get(("ServiceMonitor", "prometheus-stack", monitor_name))
        service = index.get(("Service", "kube-system", service_name))
        if not monitor or not service:
            errors.append(f"{monitor_name}: missing monitor or Service kube-system/{service_name}")
            continue
        spec = monitor["spec"]
        if "kube-system" not in spec.get("namespaceSelector", {}).get("matchNames", []):
            errors.append(f"{monitor_name}: does not select kube-system")
        selector = spec.get("selector", {})
        labels = service["metadata"].get("labels", {})
        if selector.get("matchExpressions") or not selector.get("matchLabels") or any(
            labels.get(k) != v for k, v in selector.get("matchLabels", {}).items()
        ):
            errors.append(f"{monitor_name}: selector does not match its metrics Service")
        ports = {p.get("name") for p in service["spec"].get("ports", [])}
        endpoints = spec.get("endpoints", [])
        if not endpoints or any(e.get("port") not in ports for e in endpoints):
            errors.append(f"{monitor_name}: endpoint must reference a named Service port")
    for kind, name in [
        ("DaemonSet", "kube-prometheus-stack-prometheus-node-exporter"),
        ("Deployment", "kube-prometheus-stack-kube-state-metrics"),
    ]:
        workload = index.get((kind, "prometheus-stack", name))
        if not workload:
            errors.append(f"{name}: workload was not rendered")
            continue
        for container in workload["spec"]["template"]["spec"]["containers"]:
            resources = container.get("resources") or {}
            requests, limits = resources.get("requests") or {}, resources.get("limits") or {}
            if not requests.get("cpu") or not requests.get("memory") or not limits.get("memory"):
                errors.append(f"{name}/{container['name']}: CPU/memory requests and memory limit are missing")
    return errors


def load(paths):
    return [o for path in paths for o in yaml.load_all(path.read_text(), Loader=yaml.BaseLoader)
            if isinstance(o, dict) and "kind" in o and "metadata" in o]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--argocd-capabilities", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(load(args.manifests))
        if args.argocd_capabilities:
            names = {o["metadata"]["name"] for o in load([args.argocd_capabilities])
                     if o["kind"] == "ServiceMonitor" and o["metadata"].get("namespace") == "argocd"}
            if missing := ARGO_MONITORS - names:
                errors.append(f"Argo capability-aware render is missing monitors: {sorted(missing)}")
    except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError) as exc:
        print(f"ERROR: unable to validate rendered monitoring contract: {type(exc).__name__}")
        return 1
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("Cilium metrics Services match their monitors; exporter resource baselines are present.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
