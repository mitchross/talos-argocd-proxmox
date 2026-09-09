#!/usr/bin/env python3
"""Check metrics discovery and controller baselines in rendered manifests."""
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
    for kind, namespace, name in [
        ("DaemonSet", "prometheus-stack", "kube-prometheus-stack-prometheus-node-exporter"),
        ("Deployment", "prometheus-stack", "kube-prometheus-stack-kube-state-metrics"),
        ("DaemonSet", "kube-system", "cilium-envoy"),
        ("Deployment", "external-secrets", "external-secrets"),
        ("Deployment", "snapshot-controller", "snapshot-controller"),
    ]:
        workload = index.get((kind, namespace, name))
        if not workload:
            errors.append(f"{name}: workload was not rendered")
            continue
        if name == "snapshot-controller":
            pod_spec = workload["spec"]["template"]["spec"]
            spread = pod_spec.get("affinity", {}).get("podAntiAffinity", {}).get(
                "preferredDuringSchedulingIgnoredDuringExecution", [])
            if str(workload["spec"].get("replicas", 1)) != "2":
                errors.append("snapshot-controller: expected two rendered replicas")
            if not any(t.get("podAffinityTerm", {}).get("topologyKey") ==
                       "topology.kubernetes.io/zone" for t in spread):
                errors.append("snapshot-controller: physical-host spreading preference is missing")
        for container in workload["spec"]["template"]["spec"]["containers"]:
            resources = container.get("resources") or {}
            requests, limits = resources.get("requests") or {}, resources.get("limits") or {}
            if not requests.get("cpu") or not requests.get("memory") or not limits.get("memory"):
                errors.append(f"{name}/{container['name']}: CPU/memory requests and memory limit are missing")
    return errors


DATABASES = {
    "gitea", "hindsight", "immich", "intercept", "keep", "langfuse",
    "paperless-ngx", "posthog", "surfsense", "temporal",
}


def selector_matches(selector, labels):
    """Apply ServiceMonitor LabelSelector semantics, including AND expressions."""
    if any(labels.get(key) != value for key, value in selector.get("matchLabels", {}).items()):
        return False
    for expression in selector.get("matchExpressions", []):
        key, operator = expression["key"], expression["operator"]
        values = expression.get("values", [])
        if operator == "In":
            matched = key in labels and labels[key] in values
        elif operator == "NotIn":
            matched = key not in labels or labels[key] not in values
        elif operator == "Exists":
            matched = key in labels
        elif operator == "DoesNotExist":
            matched = key not in labels
        else:
            return False
        if not matched:
            return False
    return True


def validate_databases(objects):
    """Trace expected database exporters through ServiceMonitor -> Service -> Pod."""
    # Aggregate renders can contain the same nested resource more than once.
    objects = list({(o["kind"], o["metadata"].get("namespace", "default"),
                     o["metadata"]["name"]): o for o in objects}.values())
    errors = []
    for namespace in sorted(DATABASES):
        workloads = [o for o in objects if o["kind"] == "Deployment"
                     and o["metadata"].get("namespace") == namespace
                     and any(c["name"] == "postgres-exporter"
                             for c in o["spec"]["template"]["spec"]["containers"])]
        if len(workloads) != 1:
            errors.append(f"{namespace}: expected one PostgreSQL exporter workload")
            continue
        pod = workloads[0]["spec"]["template"]
        exporter = next(c for c in pod["spec"]["containers"] if c["name"] == "postgres-exporter")
        container_ports = {p["name"]: str(p["containerPort"])
                           for p in exporter.get("ports", [])}
        services = []
        for service in objects:
            if service["kind"] != "Service" or service["metadata"].get("namespace") != namespace:
                continue
            selector = service["spec"].get("selector", {})
            if not selector or any(pod["metadata"]["labels"].get(k) != v for k, v in selector.items()):
                continue
            ports = {p["name"] for p in service["spec"].get("ports", [])
                     if str(p.get("targetPort", p["port"])) in container_ports
                     or str(p.get("targetPort", p["port"])) in container_ports.values()}
            if ports:
                services.append((service, ports))
        matches = []
        for monitor in objects:
            if monitor["kind"] != "ServiceMonitor":
                continue
            ns_selector = monitor["spec"].get("namespaceSelector", {})
            selected_namespaces = ns_selector.get("matchNames") or [monitor["metadata"].get("namespace")]
            if str(ns_selector.get("any", "false")).lower() != "true" and namespace not in selected_namespaces:
                continue
            selector = monitor["spec"].get("selector", {})
            for service, ports in services:
                if selector_matches(selector, service["metadata"].get("labels", {})):
                    matches.extend((monitor["metadata"]["name"], service["metadata"]["name"], endpoint["port"])
                                   for endpoint in monitor["spec"].get("endpoints", [])
                                   if endpoint.get("port") in ports)
        if len(matches) != 1:
            errors.append(f"{namespace}: expected one discoverable PostgreSQL metrics endpoint, got {len(matches)}")
        # New exporters deliberately cannot gate the database Service's readiness.
        if namespace in {"hindsight", "immich", "intercept", "keep", "langfuse", "surfsense"}:
            if "readinessProbe" in exporter:
                errors.append(f"{namespace}: exporter readiness must not gate database traffic")
            env = {e["name"]: e for e in exporter.get("env", [])}
            if not env.get("DATA_SOURCE_URI", {}).get("value", "").startswith("127.0.0.1:5432/"):
                errors.append(f"{namespace}: exporter must connect locally, independently of Service readiness")
            if not env.get("DATA_SOURCE_PASS", {}).get("valueFrom", {}).get("secretKeyRef"):
                errors.append(f"{namespace}: exporter password must reference the existing Secret")
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
        objects = load(args.manifests)
        errors = validate(objects) + validate_databases(objects)
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
        print("Cilium/database metrics discovery and core controller resource/replica baselines pass.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
