#!/usr/bin/env python3
"""Collect storage evidence without benchmarks, SSH, workload writes or disk changes.

Run host mode on each Proxmox host and cluster mode from an administrative client.
Reports deliberately distinguish physical-host evidence from Kubernetes evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

MAX_OUTPUT = 8 * 1024 * 1024


def run(command: list[str], structured: bool = True) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, timeout=20, check=False)
    except FileNotFoundError:
        return {"status": "unavailable", "reason": "command not installed"}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "reason": "command failed to start or timed out"}
    if result.returncode:
        return {"status": "unavailable", "reason": f"command exited {result.returncode}"}
    if len(result.stdout) > MAX_OUTPUT:
        return {"status": "unavailable", "reason": "output exceeded report limit"}
    try:
        data = json.loads(result.stdout) if structured else result.stdout.decode("utf-8")
    except (ValueError, UnicodeError):
        return {"status": "unavailable", "reason": "unexpected output format"}
    return {"status": "collected", "data": data}


def items(raw: dict, key: str) -> list[dict]:
    result = raw.get(key, {})
    data = result.get("data", {})
    return data.get("items", []) if result.get("status") == "collected" and isinstance(data, dict) else []


def conditions(obj: dict) -> dict:
    values = (obj.get("status") or {}).get("conditions") or []
    if isinstance(values, dict):
        values = values.values()
    return {str(c.get("type")): c.get("status") for c in values if isinstance(c, dict)}


def summarize_cluster(raw: dict) -> dict:
    nodes = {}
    for node in items(raw, "nodes"):
        metadata, spec = node.get("metadata", {}), node.get("spec", {})
        labels = metadata.get("labels", {})
        nodes[metadata.get("name")] = {
            "zone": labels.get("topology.kubernetes.io/zone"),
            "class": labels.get("node.vanillax.dev/class"),
            "link": labels.get("node.vanillax.dev/link"),
            "conditions": conditions(node),
            "allocatable": (node.get("status") or {}).get("allocatable", {}),
            "unschedulable": spec.get("unschedulable", False),
        }
    pvs = {p.get("metadata", {}).get("name"): p for p in items(raw, "persistentvolumes")}
    volumes = {v.get("metadata", {}).get("name"): v for v in items(raw, "longhorn_volumes")}
    replicas = items(raw, "longhorn_replicas")
    claims = []
    for pvc in items(raw, "claims"):
        metadata, spec = pvc.get("metadata", {}), pvc.get("spec", {})
        pv = pvs.get(spec.get("volumeName"), {})
        csi = pv.get("spec", {}).get("csi", {})
        handle = csi.get("volumeHandle") if csi.get("driver") == "driver.longhorn.io" else None
        volume = volumes.get(handle, {})
        placement = []
        for replica in replicas:
            rspec = replica.get("spec", {})
            if not handle or rspec.get("volumeName") != handle:
                continue
            node_name = rspec.get("nodeID")
            placement.append({
                "replica": replica.get("metadata", {}).get("name"),
                "node": node_name,
                "zone": nodes.get(node_name, {}).get("zone"),
                "disk_id": rspec.get("diskID"),
                "process_state": replica.get("status", {}).get("currentState"),
                "failed_at": rspec.get("failedAt") or None,
            })
        record = {
            "namespace": metadata.get("namespace"), "claim": metadata.get("name"),
            "phase": pvc.get("status", {}).get("phase"),
            "storage_class": spec.get("storageClassName"),
            "requested_storage": spec.get("resources", {}).get("requests", {}).get("storage"),
            "pv": spec.get("volumeName"), "csi_driver": csi.get("driver"),
            "backup_exempt": metadata.get("labels", {}).get("backup-exempt") == "true",
            "longhorn": None,
        }
        if volume:
            vstatus, vspec = volume.get("status", {}), volume.get("spec", {})
            record["longhorn"] = {
                "volume": handle, "desired_replicas": vspec.get("numberOfReplicas"),
                "state": vstatus.get("state"), "robustness": vstatus.get("robustness"),
                "engine_node": vstatus.get("currentNodeID"), "replica_placement": placement,
                "observed_zones": sorted({r["zone"] for r in placement if r["zone"]}),
                "unknown_zone_replicas": sum(r["zone"] is None for r in placement),
            }
        claims.append(record)
    disks = []
    for node in items(raw, "longhorn_nodes"):
        name = node.get("metadata", {}).get("name")
        statuses = node.get("status", {}).get("diskStatus", {}) or {}
        for disk_name, disk in (node.get("spec", {}).get("disks", {}) or {}).items():
            status = statuses.get(disk_name, {})
            disks.append({
                "node": name, "disk": disk_name, "path": disk.get("path"),
                "allow_scheduling": disk.get("allowScheduling"), "tags": disk.get("tags", []),
                "reserved_bytes": disk.get("storageReserved"), "maximum_bytes": status.get("storageMaximum"),
                "available_bytes": status.get("storageAvailable"), "scheduled_bytes": status.get("storageScheduled"),
                "conditions": conditions({"status": {"conditions": status.get("conditions", {})}}),
            })
    return {"nodes": nodes, "claims": claims, "longhorn_disks": disks}


def collect_cluster(context: str) -> dict:
    prefix = ["kubectl", "--context", context, "--request-timeout=15s", "get"]
    queries = {
        "nodes": ["nodes"], "claims": ["persistentvolumeclaims", "--all-namespaces"],
        "persistentvolumes": ["persistentvolumes"],
        "longhorn_volumes": ["volumes.longhorn.io", "-n", "longhorn-system"],
        "longhorn_replicas": ["replicas.longhorn.io", "-n", "longhorn-system"],
        "longhorn_nodes": ["nodes.longhorn.io", "-n", "longhorn-system"],
    }
    raw = {name: run(prefix + args + ["-o", "json"]) for name, args in queries.items()}
    return {
        "collection": {key: {k: v for k, v in result.items() if k != "data"} for key, result in raw.items()},
        "evidence": summarize_cluster(raw),
        "not_proven": [
            "Replica process state and declared zones do not prove independent healthy physical copies.",
            "PVC capacity and Longhorn scheduling are not physical host free space or SSD endurance.",
            "No backup freshness, restore correctness, application latency or availability test was performed.",
        ],
    }


def collect_host() -> dict:
    # Fixed read-only commands. Never sudo, SSH, SMART self-test, fio, trim or alter LVM.
    commands = {
        "block_devices": (["lsblk", "--json", "--bytes", "--output", "NAME,TYPE,SIZE,ROTA,MODEL,MOUNTPOINTS"], True),
        "volume_groups": (["vgs", "--reportformat", "json", "--units", "b", "--nosuffix", "--options", "vg_name,vg_size,vg_free"], True),
        "logical_volumes": (["lvs", "--reportformat", "json", "--units", "b", "--nosuffix", "--options", "vg_name,lv_name,lv_size,segtype,data_percent,metadata_percent"], True),
        "device_latency_sample": (["iostat", "-x", "-y", "1", "3"], False),
    }
    results = {key: run(command, structured) for key, (command, structured) in commands.items()}
    return {
        "collection": results,
        "not_proven": [
            "This is a short observation, not an IOPS benchmark or hardware qualification.",
            "SMART/endurance, PCIe/cabling errors, ZFS pools and guest-to-physical mapping require separate evidence.",
            "Free extents in a thick VG are allocation headroom, not the filesystem free space inside an allocated guest disk.",
            "Thin-pool data and metadata percentages are different from guest filesystem occupancy.",
        ],
    }


def write_report(path: Path, report: dict) -> None:
    """Create a private, new report; never overwrite a prior diagnostic artifact."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("host", "cluster"))
    parser.add_argument("--context", help="Explicit kubectl context; required for cluster mode")
    parser.add_argument("--output", type=Path, required=True, help="New private JSON report; existing files are refused")
    args = parser.parse_args()
    if args.mode == "cluster" and not args.context:
        parser.error("cluster mode requires --context")
    if args.output.exists():
        parser.error("output already exists; choose a new report filename")
    report = {"schema_version": 1, "collected_at_utc": datetime.now(timezone.utc).isoformat(), "mode": args.mode}
    try:
        if args.mode == "cluster":
            report["context"] = args.context
            report.update(collect_cluster(args.context))
        else:
            report["host"] = socket.gethostname()
            report.update(collect_host())
        write_report(args.output, report)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"Report not completed ({type(exc).__name__}); no infrastructure changes were requested.", file=sys.stderr)
        return 1
    partial = any(item.get("status") != "collected" for item in report["collection"].values())
    print(f"Wrote {'PARTIAL' if partial else 'collected'} evidence to {args.output}. This is not a cluster health certification.")
    return 2 if partial else 0


if __name__ == "__main__":
    raise SystemExit(main())
