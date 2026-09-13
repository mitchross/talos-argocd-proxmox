#!/usr/bin/env python3
"""Check this repository's Omni machine/placement contract without contacting a cluster.

This is not an Omni or Talos schema validator. Secret patches are not opened.
Host allocation totals are declared requests, not observed capacity or usage.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

import yaml

TEMPLATE = "omni/cluster-template/cluster-template-prod-v2.yaml"
CLASS_DIR = "omni/machine-classes"
LINK = "node.vanillax.dev/link"
ZONE = "topology.kubernetes.io/zone"
DISKS = "node.longhorn.io/default-disks-config"


def positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def machine_patch(doc: dict) -> dict:
    """Combine the inline machine labels/annotations/taints used by this template."""
    result = {"nodeLabels": {}, "nodeAnnotations": {}, "nodeTaints": {}}
    for patch in doc.get("patches", []):
        inline = patch.get("inline", {})
        machine = inline.get("machine", {}) if isinstance(inline, dict) else {}
        if isinstance(inline, dict) and inline.get("kind") == "KubeNodeConfig":
            machine = {"nodeLabels": inline.get("labels", {}),
                       "nodeAnnotations": inline.get("annotations", {}),
                       "nodeTaints": inline.get("taints", {})}
        for key in result:
            values = machine.get(key, {})
            if not isinstance(values, dict):
                raise ValueError(f"{key} must be a mapping")
            result[key].update(values)
    return result


def disk_matches(selector: str, size_gib: int, system_disk: bool) -> bool:
    """Evaluate this template's size-only selector subset; Talos checks CEL syntax separately."""
    matched = True
    for term in selector.split("&&"):
        term = term.strip()
        if term in ("system_disk", "!system_disk"):
            matched &= system_disk == (term == "system_disk")
            continue
        size = re.fullmatch(r"disk\.size\s*(==|>=|<=|>|<)\s*(\d+)u\s*\*\s*(GB|GiB)", term)
        if not size:
            raise ValueError("unsupported disk selector; extend the static evaluator")
        operator, number, unit = size.groups()
        left = size_gib * 2**30
        right = int(number) * (2**30 if unit == "GiB" else 10**9)
        matched &= {"==": left == right, ">=": left >= right, "<=": left <= right,
                    ">": left > right, "<": left < right}[operator]
    return matched


def check_disk_layout(doc: dict, disks: list[dict]) -> None:
    if any(d["disk_size"] <= disks[0]["disk_size"] for d in disks[1:]):
        raise ValueError("the boot disk must be uniquely smallest for fresh Omni selection")
    claims: dict[int, list[dict]] = defaultdict(list)
    for patch in doc.get("patches", []):
        volume = patch.get("inline", {})
        if volume.get("kind") not in ("UserVolumeConfig", "VolumeConfig"):
            continue
        provision = volume.get("provisioning", {})
        selector = provision.get("diskSelector", {}).get("match")
        if not selector:
            raise ValueError("provisioned volumes need an explicit disk selector")
        targets = [i for i, disk in enumerate(disks) if disk_matches(selector, disk["disk_size"], i == 0)]
        if len(targets) != 1:
            raise ValueError("volume selector must match exactly one declared disk")
        claims[targets[0]].append(volume)
    for target, volumes in claims.items():
        if target != 0 and len(volumes) > 1:
            raise ValueError("data volume selectors overlap")
        if target == 0 and len(volumes) > 1:
            # Talos 1.14 UKI/EFI/BIOS, META and STATE reserve 2202 MiB before data partitions.
            reserved = 2202 * 2**20
            for volume in volumes:
                maximum = volume["provisioning"].get("maxSize", "")
                match = re.fullmatch(r"(\d+)GiB", maximum)
                if not match:
                    raise ValueError("shared system-disk volumes need explicit GiB limits")
                reserved += int(match[1]) * 2**30
            if reserved > disks[0]["disk_size"] * 2**30:
                raise ValueError("system partitions exceed the declared boot disk")


def validate(documents: list[dict], classes: dict[str, dict]) -> tuple[list[str], dict]:
    errors: list[str] = []
    totals: dict = defaultdict(lambda: {"vcpus": 0, "memory_mib": 0, "machines": 0, "zones": set()})
    clusters = [d for d in documents if d.get("kind") == "Cluster"]
    sets = [d for d in documents if d.get("kind") in ("ControlPlane", "Workers")]
    if len(clusters) != 1:
        errors.append("Expected exactly one Cluster document")
    if not any(d.get("kind") == "ControlPlane" for d in sets):
        errors.append("No ControlPlane document found")
    seen: set[str] = set()
    for doc in sets:
        identity = str(doc.get("name") or doc["kind"])
        if identity in seen:
            errors.append(f"Duplicate machine-set identity: {identity}")
        seen.add(identity)
        ref = doc.get("machineClass") or {}
        name, count = ref.get("name"), ref.get("size")
        if not isinstance(name, str) or not name or name not in classes:
            errors.append(f"{identity}: missing referenced MachineClass {name!r}")
            continue
        if not positive_int(count):
            errors.append(f"{identity}: machineClass.size must be a positive integer")
            continue
        resource = classes[name]
        metadata = resource.get("metadata") or {}
        if metadata.get("id") != name or metadata.get("type") != "MachineClasses.omni.sidero.dev":
            errors.append(f"{name}: MachineClass metadata identity/type does not match its reference")
        provision = (resource.get("spec") or {}).get("autoprovision") or {}
        provider = provision.get("providerid")
        if not isinstance(provider, str) or not provider.strip():
            errors.append(f"{name}: missing autoprovision.providerid")
            continue
        try:
            data = yaml.safe_load(provision.get("providerdata", ""))
            if not isinstance(data, dict):
                raise ValueError("providerdata must decode to a mapping")
            for key in ("cores", "memory", "disk_size"):
                if not positive_int(data.get(key)):
                    raise ValueError(f"{key} must be a positive integer")
            if not positive_int(data.get("sockets", 1)):
                raise ValueError("sockets must be a positive integer")
            disks = [{"disk_size": data["disk_size"], "storage_selector": data.get("storage_selector")}]
            extras = data.get("additional_disks") or []
            if not isinstance(extras, list):
                raise ValueError("additional_disks must be a list")
            disks.extend(extras)
            for disk in disks:
                if not isinstance(disk, dict) or not positive_int(disk.get("disk_size")):
                    raise ValueError("every declared disk requires a positive disk_size")
                if not isinstance(disk.get("storage_selector"), str) or not disk["storage_selector"].strip():
                    raise ValueError("every declared disk requires a storage_selector")
            check_disk_layout(doc, disks)
            machine = machine_patch(doc)
            labels = machine["nodeLabels"]
            zone = labels.get(ZONE)
            if not isinstance(zone, str) or not zone:
                errors.append(f"{identity}: no inline {ZONE}; physical-host placement cannot be checked")
            else:
                totals[provider]["zones"].add(zone)
            totals[provider]["vcpus"] += data["cores"] * data.get("sockets", 1) * count
            totals[provider]["memory_mib"] += data["memory"] * count
            totals[provider]["machines"] += count
            annotations = machine["nodeAnnotations"]
            declared_disks = json.loads(annotations.get(DISKS, "[]"))
            if not isinstance(declared_disks, list):
                raise ValueError("Longhorn default-disks-config must be a JSON list")
            disk_names, paths = set(), set()
            for disk in declared_disks:
                if not isinstance(disk, dict):
                    raise ValueError("Longhorn disk entries must be mappings")
                disk_name, path = disk.get("name"), disk.get("path")
                if not isinstance(disk_name, str) or not disk_name or disk_name in disk_names:
                    raise ValueError("Longhorn disk names must be present and unique within a node")
                if not isinstance(path, str) or not path.startswith("/") or path in paths:
                    raise ValueError("Longhorn disk paths must be absolute and unique within a node")
                disk_names.add(disk_name)
                paths.add(path)
            if labels.get(LINK) == "wifi":
                if machine["nodeTaints"].get(LINK) != "wifi:NoSchedule":
                    errors.append(f"{identity}: Wi-Fi worker is missing its NoSchedule taint")
                if any(d.get("allowScheduling", True) is not False for d in declared_disks):
                    errors.append(f"{identity}: Wi-Fi Longhorn disks must explicitly disable scheduling")
                node_tags = json.loads(annotations.get("node.longhorn.io/default-node-tags", "[]"))
                if "wired-storage" in node_tags:
                    errors.append(f"{identity}: Wi-Fi worker cannot carry wired-storage")
        except (yaml.YAMLError, ValueError, TypeError, AttributeError, KeyError):
            # Do not print providerdata: a malformed configuration can contain credentials.
            errors.append(f"{name}: invalid providerdata or inline placement/disk declaration; inspect that class and machine set")
    for provider, values in totals.items():
        if len(values["zones"]) > 1:
            errors.append(f"{provider}: one provider is assigned multiple physical-host zones: {sorted(values['zones'])}")
        values["zones"] = sorted(values["zones"])
    return errors, dict(totals)


def load(root: Path) -> tuple[list[dict], dict[str, dict]]:
    documents = [d for d in yaml.safe_load_all((root / TEMPLATE).read_text()) if isinstance(d, dict)]
    classes = {}
    for doc in documents:
        if doc.get("kind") not in ("ControlPlane", "Workers"):
            continue
        name = (doc.get("machineClass") or {}).get("name")
        if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
            continue
        path = root / CLASS_DIR / f"{name}.yaml"
        if path.is_file():
            resource = yaml.safe_load(path.read_text())
            if not isinstance(resource, dict):
                raise ValueError("MachineClass must be a mapping")
            classes[name] = resource
    return documents, classes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors, totals = validate(*load(args.root))
    except (OSError, yaml.YAMLError, ValueError, TypeError, AttributeError):
        print("FAIL: unable to read template or referenced MachineClass YAML", file=sys.stderr)
        return 1
    print(json.dumps({"declared_provider_allocations": totals, "errors": errors}, indent=2))
    print("Allocation totals are requests, not host capacity, usage, or reservations. Secret patches and live Omni state were not checked.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
