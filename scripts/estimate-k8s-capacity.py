#!/usr/bin/env python3
"""
Kubernetes capacity estimator for Talos/Proxmox homelab clusters.

Read-only. Uses:
  - kubectl get nodes -o json
  - kubectl get pods -A -o json
  - kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes
  - kubectl get --raw /apis/metrics.k8s.io/v1beta1/pods

Outputs:
  - summary.md
  - raw JSON snapshots
  - CSV sample series
  - pod/request inventory CSV

Example:
  ./estimate-k8s-capacity.py --duration 3600 --interval 60
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


CPU_MILLI = 1000
MEM_GIB = 1024 ** 3


def sh_json(args: List[str]) -> Any:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\nSTDERR:\n{p.stderr}")
    return json.loads(p.stdout)


def sh_text(args: List[str]) -> str:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\nSTDERR:\n{p.stderr}")
    return p.stdout


def parse_cpu_to_millicores(v: Optional[str]) -> int:
    if not v:
        return 0
    s = str(v).strip()
    if s.endswith("n"):
        return math.ceil(float(s[:-1]) / 1_000_000)
    if s.endswith("u"):
        return math.ceil(float(s[:-1]) / 1_000)
    if s.endswith("m"):
        return int(float(s[:-1]))
    return int(float(s) * 1000)


def parse_mem_to_bytes(v: Optional[str]) -> int:
    if not v:
        return 0
    s = str(v).strip()

    # Kubernetes binary suffixes.
    units = {
        "Ki": 1024,
        "Mi": 1024 ** 2,
        "Gi": 1024 ** 3,
        "Ti": 1024 ** 4,
        "Pi": 1024 ** 5,
        "Ei": 1024 ** 6,
        # Decimal suffixes.
        "K": 1000,
        "M": 1000 ** 2,
        "G": 1000 ** 3,
        "T": 1000 ** 4,
        "P": 1000 ** 5,
        "E": 1000 ** 6,
    }

    m = re.match(r"^([0-9.]+)([A-Za-z]+)?$", s)
    if not m:
        return 0
    num = float(m.group(1))
    unit = m.group(2) or ""
    return int(num * units.get(unit, 1))


def fmt_cpu(mcpu: float) -> str:
    return f"{mcpu / 1000:.2f} cores"


def fmt_mem(b: float) -> str:
    return f"{b / MEM_GIB:.1f} GiB"


def pct(part: float, whole: float) -> str:
    if whole <= 0:
        return "n/a"
    return f"{(part / whole) * 100:.1f}%"


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return vals[int(k)]
    return vals[f] * (c - k) + vals[c] * (k - f)


def ceil_gib(bytes_val: float, step_gib: int = 8) -> int:
    gib = bytes_val / MEM_GIB
    return int(math.ceil(gib / step_gib) * step_gib)


def ceil_cores(mcpu: float, step: int = 2) -> int:
    cores = mcpu / 1000
    return int(math.ceil(cores / step) * step)


def node_role(node: Dict[str, Any]) -> str:
    labels = node.get("metadata", {}).get("labels", {})
    if labels.get("nvidia.com/gpu.present") == "true" or int(node.get("status", {}).get("allocatable", {}).get("nvidia.com/gpu", "0") or 0) > 0:
        return "gpu-worker"
    if "node-role.kubernetes.io/control-plane" in labels or "node-role.kubernetes.io/master" in labels:
        return "control-plane"
    return "worker"


def owner_name(pod: Dict[str, Any]) -> str:
    meta = pod.get("metadata", {})
    owners = meta.get("ownerReferences") or []
    if not owners:
        return pod.get("metadata", {}).get("name", "")
    # Usually ReplicaSet; still useful.
    o = owners[0]
    return f"{o.get('kind', '')}/{o.get('name', '')}"


def pod_resource_totals(pod: Dict[str, Any]) -> Dict[str, int]:
    totals = {
        "req_cpu_m": 0,
        "req_mem_b": 0,
        "lim_cpu_m": 0,
        "lim_mem_b": 0,
        "req_gpu": 0,
        "lim_gpu": 0,
        "containers": 0,
        "containers_missing_cpu_req": 0,
        "containers_missing_mem_req": 0,
    }

    for c in pod.get("spec", {}).get("containers", []):
        totals["containers"] += 1
        resources = c.get("resources", {})
        req = resources.get("requests", {})
        lim = resources.get("limits", {})

        if "cpu" not in req:
            totals["containers_missing_cpu_req"] += 1
        if "memory" not in req:
            totals["containers_missing_mem_req"] += 1

        totals["req_cpu_m"] += parse_cpu_to_millicores(req.get("cpu"))
        totals["req_mem_b"] += parse_mem_to_bytes(req.get("memory"))
        totals["lim_cpu_m"] += parse_cpu_to_millicores(lim.get("cpu"))
        totals["lim_mem_b"] += parse_mem_to_bytes(lim.get("memory"))

        try:
            totals["req_gpu"] += int(req.get("nvidia.com/gpu", 0) or 0)
        except Exception:
            pass
        try:
            totals["lim_gpu"] += int(lim.get("nvidia.com/gpu", 0) or 0)
        except Exception:
            pass

    return totals


def get_metrics() -> Tuple[Dict[str, Dict[str, int]], Dict[Tuple[str, str], Dict[str, int]]]:
    node_metrics_raw = sh_json(["kubectl", "get", "--raw", "/apis/metrics.k8s.io/v1beta1/nodes"])
    pod_metrics_raw = sh_json(["kubectl", "get", "--raw", "/apis/metrics.k8s.io/v1beta1/pods"])

    node_metrics: Dict[str, Dict[str, int]] = {}
    for item in node_metrics_raw.get("items", []):
        name = item["metadata"]["name"]
        usage = item.get("usage", {})
        node_metrics[name] = {
            "cpu_m": parse_cpu_to_millicores(usage.get("cpu")),
            "mem_b": parse_mem_to_bytes(usage.get("memory")),
        }

    pod_metrics: Dict[Tuple[str, str], Dict[str, int]] = {}
    for item in pod_metrics_raw.get("items", []):
        ns = item["metadata"]["namespace"]
        name = item["metadata"]["name"]
        cpu_m = 0
        mem_b = 0
        for c in item.get("containers", []):
            usage = c.get("usage", {})
            cpu_m += parse_cpu_to_millicores(usage.get("cpu"))
            mem_b += parse_mem_to_bytes(usage.get("memory"))
        pod_metrics[(ns, name)] = {"cpu_m": cpu_m, "mem_b": mem_b}

    return node_metrics, pod_metrics


def summarize_samples(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    keys = [
        "cluster_cpu_m",
        "cluster_mem_b",
    ]

    for k in keys:
        vals = [float(s[k]) for s in samples]
        out[k] = {
            "min": min(vals) if vals else 0,
            "avg": statistics.mean(vals) if vals else 0,
            "p50": percentile(vals, 50),
            "p95": percentile(vals, 95),
            "max": max(vals) if vals else 0,
        }

    # By node role.
    roles = sorted({r for s in samples for r in s.get("roles", {}).keys()})
    out["roles"] = {}
    for role in roles:
        out["roles"][role] = {}
        for metric in ["cpu_m", "mem_b"]:
            vals = [float(s.get("roles", {}).get(role, {}).get(metric, 0)) for s in samples]
            out["roles"][role][metric] = {
                "avg": statistics.mean(vals) if vals else 0,
                "p95": percentile(vals, 95),
                "max": max(vals) if vals else 0,
            }

    return out


def make_recommendations(
    nodes: List[Dict[str, Any]],
    pods: List[Dict[str, Any]],
    samples_summary: Dict[str, Any],
    node_inventory: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Produce conservative-ish estimates.

    These are not scheduler-perfect. They are capacity planning estimates:
      - observed-based = p95 live usage * headroom
      - request-based = current pod requests
      - N+1 worker = fit worker role workload if one worker disappears
    """

    role_counts = defaultdict(int)
    role_alloc_cpu = defaultdict(int)
    role_alloc_mem = defaultdict(int)

    for n in nodes:
        name = n["metadata"]["name"]
        role = node_inventory[name]["role"]
        role_counts[role] += 1
        role_alloc_cpu[role] += node_inventory[name]["alloc_cpu_m"]
        role_alloc_mem[role] += node_inventory[name]["alloc_mem_b"]

    role_req_cpu = defaultdict(int)
    role_req_mem = defaultdict(int)
    role_lim_cpu = defaultdict(int)
    role_lim_mem = defaultdict(int)

    for pod in pods:
        phase = pod.get("status", {}).get("phase")
        node = pod.get("spec", {}).get("nodeName")
        if not node or phase in ("Succeeded", "Failed"):
            continue
        role = node_inventory.get(node, {}).get("role", "unknown")
        totals = pod_resource_totals(pod)
        role_req_cpu[role] += totals["req_cpu_m"]
        role_req_mem[role] += totals["req_mem_b"]
        role_lim_cpu[role] += totals["lim_cpu_m"]
        role_lim_mem[role] += totals["lim_mem_b"]

    rec: Dict[str, Any] = {"roles": {}, "cluster": {}}

    # Tunable planning assumptions.
    cpu_observed_headroom = 1.50
    mem_observed_headroom = 1.75
    mem_request_headroom = 1.25
    cpu_request_headroom = 1.15

    for role, count in sorted(role_counts.items()):
        observed_cpu_p95 = samples_summary.get("roles", {}).get(role, {}).get("cpu_m", {}).get("p95", 0)
        observed_mem_p95 = samples_summary.get("roles", {}).get(role, {}).get("mem_b", {}).get("p95", 0)

        req_cpu = role_req_cpu[role]
        req_mem = role_req_mem[role]

        observed_based_cpu = observed_cpu_p95 * cpu_observed_headroom
        observed_based_mem = observed_mem_p95 * mem_observed_headroom

        request_based_cpu = req_cpu * cpu_request_headroom
        request_based_mem = req_mem * mem_request_headroom

        role_cpu_need = max(observed_based_cpu, request_based_cpu)
        role_mem_need = max(observed_based_mem, request_based_mem)

        # N+1 only really makes sense for worker pools with count > 1.
        per_node_cpu_nplus1 = None
        per_node_mem_nplus1 = None
        if role in ("worker", "gpu-worker") and count > 1:
            denominator = max(count - 1, 1)
            per_node_cpu_nplus1 = role_cpu_need / denominator
            per_node_mem_nplus1 = role_mem_need / denominator
        elif role == "worker" and count == 1:
            per_node_cpu_nplus1 = role_cpu_need
            per_node_mem_nplus1 = role_mem_need

        rec["roles"][role] = {
            "count": count,
            "alloc_cpu_m": role_alloc_cpu[role],
            "alloc_mem_b": role_alloc_mem[role],
            "req_cpu_m": req_cpu,
            "req_mem_b": req_mem,
            "observed_cpu_p95_m": observed_cpu_p95,
            "observed_mem_p95_b": observed_mem_p95,
            "estimated_role_cpu_need_m": role_cpu_need,
            "estimated_role_mem_need_b": role_mem_need,
            "suggested_total_cpu_cores": ceil_cores(role_cpu_need, 2),
            "suggested_total_mem_gib": ceil_gib(role_mem_need, 8),
            "nplus1_per_node_cpu_cores": ceil_cores(per_node_cpu_nplus1, 2) if per_node_cpu_nplus1 else None,
            "nplus1_per_node_mem_gib": ceil_gib(per_node_mem_nplus1, 8) if per_node_mem_nplus1 else None,
        }

    cluster_cpu_p95 = samples_summary["cluster_cpu_m"]["p95"]
    cluster_mem_p95 = samples_summary["cluster_mem_b"]["p95"]
    total_req_cpu = sum(role_req_cpu.values())
    total_req_mem = sum(role_req_mem.values())

    cluster_cpu_need = max(cluster_cpu_p95 * cpu_observed_headroom, total_req_cpu * cpu_request_headroom)
    cluster_mem_need = max(cluster_mem_p95 * mem_observed_headroom, total_req_mem * mem_request_headroom)

    rec["cluster"] = {
        "observed_cpu_p95_m": cluster_cpu_p95,
        "observed_mem_p95_b": cluster_mem_p95,
        "req_cpu_m": total_req_cpu,
        "req_mem_b": total_req_mem,
        "estimated_cpu_need_m": cluster_cpu_need,
        "estimated_mem_need_b": cluster_mem_need,
        "suggested_cpu_cores": ceil_cores(cluster_cpu_need, 4),
        "suggested_mem_gib": ceil_gib(cluster_mem_need, 16),
    }

    return rec


def write_summary(
    outdir: Path,
    nodes: List[Dict[str, Any]],
    pods: List[Dict[str, Any]],
    node_inventory: Dict[str, Dict[str, Any]],
    pod_inventory: List[Dict[str, Any]],
    samples: List[Dict[str, Any]],
    samples_summary: Dict[str, Any],
    rec: Dict[str, Any],
    args: argparse.Namespace,
) -> None:
    total_alloc_cpu = sum(v["alloc_cpu_m"] for v in node_inventory.values())
    total_alloc_mem = sum(v["alloc_mem_b"] for v in node_inventory.values())
    total_capacity_cpu = sum(v["cap_cpu_m"] for v in node_inventory.values())
    total_capacity_mem = sum(v["cap_mem_b"] for v in node_inventory.values())

    total_req_cpu = sum(p["req_cpu_m"] for p in pod_inventory if p["phase"] not in ("Succeeded", "Failed"))
    total_req_mem = sum(p["req_mem_b"] for p in pod_inventory if p["phase"] not in ("Succeeded", "Failed"))
    total_lim_cpu = sum(p["lim_cpu_m"] for p in pod_inventory if p["phase"] not in ("Succeeded", "Failed"))
    total_lim_mem = sum(p["lim_mem_b"] for p in pod_inventory if p["phase"] not in ("Succeeded", "Failed"))

    missing_cpu_req = sum(p["containers_missing_cpu_req"] for p in pod_inventory if p["phase"] not in ("Succeeded", "Failed"))
    missing_mem_req = sum(p["containers_missing_mem_req"] for p in pod_inventory if p["phase"] not in ("Succeeded", "Failed"))
    total_containers = sum(p["containers"] for p in pod_inventory if p["phase"] not in ("Succeeded", "Failed"))

    latest = samples[-1] if samples else {}

    top_mem_pods = sorted(
        [p for p in pod_inventory if p["observed_mem_b_max"] > 0],
        key=lambda x: x["observed_mem_b_max"],
        reverse=True,
    )[:25]

    top_cpu_pods = sorted(
        [p for p in pod_inventory if p["observed_cpu_m_max"] > 0],
        key=lambda x: x["observed_cpu_m_max"],
        reverse=True,
    )[:25]

    ns_agg = defaultdict(lambda: {"req_cpu_m": 0, "req_mem_b": 0, "obs_cpu_m_max": 0, "obs_mem_b_max": 0})
    for p in pod_inventory:
        if p["phase"] in ("Succeeded", "Failed"):
            continue
        ns = p["namespace"]
        ns_agg[ns]["req_cpu_m"] += p["req_cpu_m"]
        ns_agg[ns]["req_mem_b"] += p["req_mem_b"]
        ns_agg[ns]["obs_cpu_m_max"] += p["observed_cpu_m_max"]
        ns_agg[ns]["obs_mem_b_max"] += p["observed_mem_b_max"]

    top_ns_mem = sorted(ns_agg.items(), key=lambda kv: kv[1]["obs_mem_b_max"], reverse=True)[:20]
    top_ns_cpu = sorted(ns_agg.items(), key=lambda kv: kv[1]["obs_cpu_m_max"], reverse=True)[:20]

    lines: List[str] = []
    lines.append("# Kubernetes Capacity Estimate")
    lines.append("")
    lines.append(f"- Context: `{args.context}`")
    lines.append(f"- Label: `{args.label}`")
    lines.append(f"- Samples: `{len(samples)}`")
    lines.append(f"- Duration requested: `{args.duration}s`")
    lines.append(f"- Interval: `{args.interval}s`")
    lines.append(f"- Generated UTC: `{dt.datetime.utcnow().isoformat()}Z`")
    lines.append("")
    lines.append("## Cluster capacity")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Node count | {len(nodes)} |")
    lines.append(f"| Capacity CPU | {fmt_cpu(total_capacity_cpu)} |")
    lines.append(f"| Allocatable CPU | {fmt_cpu(total_alloc_cpu)} |")
    lines.append(f"| Capacity memory | {fmt_mem(total_capacity_mem)} |")
    lines.append(f"| Allocatable memory | {fmt_mem(total_alloc_mem)} |")
    lines.append(f"| Pod CPU requests | {fmt_cpu(total_req_cpu)} ({pct(total_req_cpu, total_alloc_cpu)} allocatable) |")
    lines.append(f"| Pod memory requests | {fmt_mem(total_req_mem)} ({pct(total_req_mem, total_alloc_mem)} allocatable) |")
    lines.append(f"| Pod CPU limits | {fmt_cpu(total_lim_cpu)} |")
    lines.append(f"| Pod memory limits | {fmt_mem(total_lim_mem)} |")
    lines.append(f"| Containers missing CPU request | {missing_cpu_req}/{total_containers} |")
    lines.append(f"| Containers missing memory request | {missing_mem_req}/{total_containers} |")
    lines.append("")
    lines.append("## Observed usage from metrics-server")
    lines.append("")
    lines.append("| Metric | Avg | P95 | Max |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| CPU | {fmt_cpu(samples_summary['cluster_cpu_m']['avg'])} | "
        f"{fmt_cpu(samples_summary['cluster_cpu_m']['p95'])} | "
        f"{fmt_cpu(samples_summary['cluster_cpu_m']['max'])} |"
    )
    lines.append(
        f"| Memory | {fmt_mem(samples_summary['cluster_mem_b']['avg'])} | "
        f"{fmt_mem(samples_summary['cluster_mem_b']['p95'])} | "
        f"{fmt_mem(samples_summary['cluster_mem_b']['max'])} |"
    )
    lines.append("")
    lines.append("## Estimated cluster need")
    lines.append("")
    lines.append("This is a planning estimate, not a scheduler proof. It uses the larger of observed P95-with-headroom and current requests-with-headroom.")
    lines.append("")
    lines.append("| Estimate | CPU | Memory |")
    lines.append("|---|---:|---:|")
    lines.append(
        f"| Observed P95 | {fmt_cpu(rec['cluster']['observed_cpu_p95_m'])} | "
        f"{fmt_mem(rec['cluster']['observed_mem_p95_b'])} |"
    )
    lines.append(
        f"| Requests | {fmt_cpu(rec['cluster']['req_cpu_m'])} | "
        f"{fmt_mem(rec['cluster']['req_mem_b'])} |"
    )
    lines.append(
        f"| Estimated need | {fmt_cpu(rec['cluster']['estimated_cpu_need_m'])} | "
        f"{fmt_mem(rec['cluster']['estimated_mem_need_b'])} |"
    )
    lines.append(
        f"| Rounded planning target | {rec['cluster']['suggested_cpu_cores']} cores | "
        f"{rec['cluster']['suggested_mem_gib']} GiB |"
    )
    lines.append("")
    lines.append("## By node role")
    lines.append("")
    lines.append("| Role | Nodes | Alloc CPU | Alloc Mem | Req CPU | Req Mem | Obs CPU P95 | Obs Mem P95 | Est Total CPU | Est Total Mem | N+1 per-node CPU | N+1 per-node Mem |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for role, r in rec["roles"].items():
        lines.append(
            f"| {role} | {r['count']} | "
            f"{fmt_cpu(r['alloc_cpu_m'])} | {fmt_mem(r['alloc_mem_b'])} | "
            f"{fmt_cpu(r['req_cpu_m'])} | {fmt_mem(r['req_mem_b'])} | "
            f"{fmt_cpu(r['observed_cpu_p95_m'])} | {fmt_mem(r['observed_mem_p95_b'])} | "
            f"{r['suggested_total_cpu_cores']} cores | {r['suggested_total_mem_gib']} GiB | "
            f"{str(r['nplus1_per_node_cpu_cores']) + ' cores' if r['nplus1_per_node_cpu_cores'] else 'n/a'} | "
            f"{str(r['nplus1_per_node_mem_gib']) + ' GiB' if r['nplus1_per_node_mem_gib'] else 'n/a'} |"
        )
    lines.append("")
    lines.append("## Current nodes")
    lines.append("")
    lines.append("| Node | Role | Alloc CPU | Alloc Mem | Latest CPU | Latest Mem |")
    lines.append("|---|---|---:|---:|---:|---:|")
    latest_nodes = latest.get("nodes", {})
    for name, inv in sorted(node_inventory.items()):
        m = latest_nodes.get(name, {})
        lines.append(
            f"| {name} | {inv['role']} | "
            f"{fmt_cpu(inv['alloc_cpu_m'])} | {fmt_mem(inv['alloc_mem_b'])} | "
            f"{fmt_cpu(m.get('cpu_m', 0))} | {fmt_mem(m.get('mem_b', 0))} |"
        )
    lines.append("")
    lines.append("## Top namespaces by observed memory")
    lines.append("")
    lines.append("| Namespace | Observed max memory sum | Observed max CPU sum | Requests memory | Requests CPU |")
    lines.append("|---|---:|---:|---:|---:|")
    for ns, a in top_ns_mem:
        lines.append(
            f"| {ns} | {fmt_mem(a['obs_mem_b_max'])} | {fmt_cpu(a['obs_cpu_m_max'])} | "
            f"{fmt_mem(a['req_mem_b'])} | {fmt_cpu(a['req_cpu_m'])} |"
        )
    lines.append("")
    lines.append("## Top namespaces by observed CPU")
    lines.append("")
    lines.append("| Namespace | Observed max CPU sum | Observed max memory sum | Requests CPU | Requests memory |")
    lines.append("|---|---:|---:|---:|---:|")
    for ns, a in top_ns_cpu:
        lines.append(
            f"| {ns} | {fmt_cpu(a['obs_cpu_m_max'])} | {fmt_mem(a['obs_mem_b_max'])} | "
            f"{fmt_cpu(a['req_cpu_m'])} | {fmt_mem(a['req_mem_b'])} |"
        )
    lines.append("")
    lines.append("## Top pods by observed memory")
    lines.append("")
    lines.append("| Namespace | Pod | Node | Owner | Obs max mem | Obs max CPU | Req mem | Req CPU | Lim mem | Lim CPU |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for p in top_mem_pods:
        lines.append(
            f"| {p['namespace']} | {p['pod']} | {p['node']} | {p['owner']} | "
            f"{fmt_mem(p['observed_mem_b_max'])} | {fmt_cpu(p['observed_cpu_m_max'])} | "
            f"{fmt_mem(p['req_mem_b'])} | {fmt_cpu(p['req_cpu_m'])} | "
            f"{fmt_mem(p['lim_mem_b'])} | {fmt_cpu(p['lim_cpu_m'])} |"
        )
    lines.append("")
    lines.append("## Top pods by observed CPU")
    lines.append("")
    lines.append("| Namespace | Pod | Node | Owner | Obs max CPU | Obs max mem | Req CPU | Req mem | Lim CPU | Lim mem |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for p in top_cpu_pods:
        lines.append(
            f"| {p['namespace']} | {p['pod']} | {p['node']} | {p['owner']} | "
            f"{fmt_cpu(p['observed_cpu_m_max'])} | {fmt_mem(p['observed_mem_b_max'])} | "
            f"{fmt_cpu(p['req_cpu_m'])} | {fmt_mem(p['req_mem_b'])} | "
            f"{fmt_cpu(p['lim_cpu_m'])} | {fmt_mem(p['lim_mem_b'])} |"
        )
    lines.append("")
    lines.append("## How to interpret")
    lines.append("")
    lines.append("- **Observed usage** is real usage during this sample window only.")
    lines.append("- **Requests** are what the scheduler reserves. If requests are missing or too low, observed usage is more useful.")
    lines.append("- **Estimated need** intentionally includes headroom. It is not the minimum bootable cluster size.")
    lines.append("- **N+1 per-node** is the rough per-node size needed for a role to survive losing one node in that role.")
    lines.append("- For your hardware decision, compare the rounded planning target against possible VM layouts like 384G, 512G, etc.")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- `samples.csv`: cluster and role time series")
    lines.append("- `node_inventory.csv`: node capacity and role classification")
    lines.append("- `pod_inventory.csv`: pod requests, limits, observed max usage")
    lines.append("- `raw/`: raw Kubernetes JSON snapshots")
    lines.append("")

    (outdir / "summary.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=900, help="sample duration in seconds")
    parser.add_argument("--interval", type=int, default=30, help="sample interval in seconds")
    parser.add_argument("--label", default="baseline", help="label for this run")
    args = parser.parse_args()

    try:
        context = sh_text(["kubectl", "config", "current-context"]).strip()
    except Exception as e:
        print(f"ERROR: kubectl not working: {e}", file=sys.stderr)
        return 1

    args.context = context

    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_ctx = re.sub(r"[^A-Za-z0-9_.-]+", "_", context)
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.label)
    outdir = Path(f"k8s-capacity-estimate-{safe_ctx}-{safe_label}-{ts}")
    rawdir = outdir / "raw"
    outdir.mkdir(parents=True, exist_ok=True)
    rawdir.mkdir(parents=True, exist_ok=True)

    print(f"Writing to: {outdir}")
    print(f"Context: {context}")
    print(f"Duration: {args.duration}s, interval: {args.interval}s")
    print("Read-only collection starting...")

    nodes_raw = sh_json(["kubectl", "get", "nodes", "-o", "json"])
    pods_raw = sh_json(["kubectl", "get", "pods", "-A", "-o", "json"])

    (rawdir / "nodes.json").write_text(json.dumps(nodes_raw, indent=2))
    (rawdir / "pods-initial.json").write_text(json.dumps(pods_raw, indent=2))

    nodes = nodes_raw.get("items", [])
    pods = pods_raw.get("items", [])

    node_inventory: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        name = n["metadata"]["name"]
        cap = n.get("status", {}).get("capacity", {})
        alloc = n.get("status", {}).get("allocatable", {})
        role = node_role(n)

        node_inventory[name] = {
            "node": name,
            "role": role,
            "cap_cpu_m": parse_cpu_to_millicores(cap.get("cpu")),
            "cap_mem_b": parse_mem_to_bytes(cap.get("memory")),
            "alloc_cpu_m": parse_cpu_to_millicores(alloc.get("cpu")),
            "alloc_mem_b": parse_mem_to_bytes(alloc.get("memory")),
            "gpu_allocatable": int(alloc.get("nvidia.com/gpu", 0) or 0),
        }

    pod_inventory_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for pod in pods:
        ns = pod.get("metadata", {}).get("namespace", "")
        name = pod.get("metadata", {}).get("name", "")
        node = pod.get("spec", {}).get("nodeName", "")
        phase = pod.get("status", {}).get("phase", "")
        totals = pod_resource_totals(pod)

        pod_inventory_map[(ns, name)] = {
            "namespace": ns,
            "pod": name,
            "node": node,
            "node_role": node_inventory.get(node, {}).get("role", "unscheduled"),
            "phase": phase,
            "owner": owner_name(pod),
            **totals,
            "observed_cpu_m_max": 0,
            "observed_mem_b_max": 0,
        }

    samples: List[Dict[str, Any]] = []
    start = time.time()
    sample_num = 0

    while True:
        sample_num += 1
        now = dt.datetime.utcnow().isoformat() + "Z"

        try:
            node_metrics, pod_metrics = get_metrics()
        except Exception as e:
            print(f"WARN: metrics collection failed: {e}", file=sys.stderr)
            if not samples:
                print("ERROR: no metrics collected. Is metrics-server installed?", file=sys.stderr)
                return 2
            break

        cluster_cpu_m = sum(v["cpu_m"] for v in node_metrics.values())
        cluster_mem_b = sum(v["mem_b"] for v in node_metrics.values())

        roles = defaultdict(lambda: {"cpu_m": 0, "mem_b": 0})
        for node, m in node_metrics.items():
            role = node_inventory.get(node, {}).get("role", "unknown")
            roles[role]["cpu_m"] += m["cpu_m"]
            roles[role]["mem_b"] += m["mem_b"]

        for (ns, pod), m in pod_metrics.items():
            if (ns, pod) in pod_inventory_map:
                pod_inventory_map[(ns, pod)]["observed_cpu_m_max"] = max(
                    pod_inventory_map[(ns, pod)]["observed_cpu_m_max"], m["cpu_m"]
                )
                pod_inventory_map[(ns, pod)]["observed_mem_b_max"] = max(
                    pod_inventory_map[(ns, pod)]["observed_mem_b_max"], m["mem_b"]
                )

        sample = {
            "ts": now,
            "cluster_cpu_m": cluster_cpu_m,
            "cluster_mem_b": cluster_mem_b,
            "roles": dict(roles),
            "nodes": node_metrics,
        }
        samples.append(sample)

        print(
            f"[{sample_num}] {now} cluster={fmt_cpu(cluster_cpu_m)}, {fmt_mem(cluster_mem_b)}",
            flush=True,
        )

        elapsed = time.time() - start
        if elapsed >= args.duration:
            break

        sleep_for = max(1, min(args.interval, args.duration - elapsed))
        time.sleep(sleep_for)

    # Refresh pods at end to catch reschedules/new pods.
    pods_final_raw = sh_json(["kubectl", "get", "pods", "-A", "-o", "json"])
    (rawdir / "pods-final.json").write_text(json.dumps(pods_final_raw, indent=2))

    pod_inventory = list(pod_inventory_map.values())
    samples_summary = summarize_samples(samples)
    rec = make_recommendations(nodes, pods, samples_summary, node_inventory)

    # Write CSVs.
    with (outdir / "samples.csv").open("w", newline="") as f:
        fieldnames = [
            "ts",
            "cluster_cpu_m",
            "cluster_mem_b",
            "control_plane_cpu_m",
            "control_plane_mem_b",
            "worker_cpu_m",
            "worker_mem_b",
            "gpu_worker_cpu_m",
            "gpu_worker_mem_b",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in samples:
            roles = s.get("roles", {})
            w.writerow({
                "ts": s["ts"],
                "cluster_cpu_m": s["cluster_cpu_m"],
                "cluster_mem_b": s["cluster_mem_b"],
                "control_plane_cpu_m": roles.get("control-plane", {}).get("cpu_m", 0),
                "control_plane_mem_b": roles.get("control-plane", {}).get("mem_b", 0),
                "worker_cpu_m": roles.get("worker", {}).get("cpu_m", 0),
                "worker_mem_b": roles.get("worker", {}).get("mem_b", 0),
                "gpu_worker_cpu_m": roles.get("gpu-worker", {}).get("cpu_m", 0),
                "gpu_worker_mem_b": roles.get("gpu-worker", {}).get("mem_b", 0),
            })

    with (outdir / "node_inventory.csv").open("w", newline="") as f:
        fieldnames = ["node", "role", "cap_cpu_m", "cap_mem_b", "alloc_cpu_m", "alloc_mem_b", "gpu_allocatable"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for v in sorted(node_inventory.values(), key=lambda x: (x["role"], x["node"])):
            w.writerow(v)

    with (outdir / "pod_inventory.csv").open("w", newline="") as f:
        fieldnames = [
            "namespace", "pod", "node", "node_role", "phase", "owner",
            "req_cpu_m", "req_mem_b", "lim_cpu_m", "lim_mem_b",
            "req_gpu", "lim_gpu",
            "containers", "containers_missing_cpu_req", "containers_missing_mem_req",
            "observed_cpu_m_max", "observed_mem_b_max",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for p in sorted(pod_inventory, key=lambda x: (x["namespace"], x["pod"])):
            w.writerow({k: p.get(k, "") for k in fieldnames})

    (outdir / "recommendations.json").write_text(json.dumps(rec, indent=2))
    write_summary(outdir, nodes, pods, node_inventory, pod_inventory, samples, samples_summary, rec, args)

    print("")
    print("Done.")
    print(f"Summary: {outdir / 'summary.md'}")
    print(f"Folder:  {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
