#!/usr/bin/env python3
"""Generate and validate every production machine role using version-matched talosctl.

No cluster API is contacted. Synthetic cluster secrets are used. The private
registry patch is skipped unless --include-private-patches is explicitly set.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml

TEMPLATE = "omni/cluster-template/cluster-template-prod-v2.yaml"
PRIVATE_PATCH = "patches/docker-hub-auth.yaml"


def behavior_errors(documents: list[dict], role: str, kubernetes_version: str) -> list[str]:
    errors = []
    kinds = {d.get("kind"): d for d in documents}
    machine = kinds[None]["machine"]
    kubelet = machine.get("kubelet", {})
    if kubelet.get("image") != f"ghcr.io/siderolabs/kubelet:{kubernetes_version}":
        errors.append("legacy kubelet image must match the cluster Kubernetes version")
    if kubelet.get("defaultRuntimeSeccompProfileEnabled") is not True:
        errors.append("preserve the fresh generator's runtime seccomp default")
    if kubelet.get("disableManifestsDirectory") is not True:
        errors.append("preserve the fresh generator's disabled manifests directory")
    if "KubeletConfig" in kinds:
        errors.append("legacy kubelet mount configuration must have a single owner")
    if kinds.get("SecurityProfileConfig", {}).get("workloadIsolation") is not True:
        errors.append("preserve the fresh generator's workload isolation default")
    node = kinds.get("KubeNodeConfig", {})
    if role == "controlplane":
        if "KubeFlannelCNIConfig" in kinds or kinds.get("KubeProxyConfig", {}).get("enabled") is not False:
            errors.append("Cilium must own CNI and kube-proxy replacement")
        if node.get("taints", {}).get("node-role.kubernetes.io/control-plane") != "NoSchedule":
            errors.append("preserve the control-plane NoSchedule taint")
    else:
        if node.get("nodeIP", {}).get("validSubnets") != ["192.168.10.0/24"]:
            errors.append("worker node IP must come from the main LAN")
        mounts = kubelet.get("extraMounts", [])
        if not any(m.get("source") == "/var/local/longhorn"
                   and m.get("destination") == "/var/lib/longhorn"
                   and m.get("type") == "bind"
                   and {"bind", "rshared", "rw"} <= set(m.get("options", [])) for m in mounts):
            errors.append("Longhorn's shared writable kubelet bind mount is missing")
    return errors


def validate(root: Path, output: Path, include_private: bool, binary: str) -> list[dict]:
    template = root / TEMPLATE
    documents = list(yaml.safe_load_all(template.read_text()))
    cluster = next(d for d in documents if d["kind"] == "Cluster")
    talos_version = cluster["talos"]["version"]
    kubernetes_version = cluster["kubernetes"]["version"]
    version = subprocess.run([binary, "version", "--client", "--short"], capture_output=True, text=True, timeout=30)
    if version.returncode or talos_version not in version.stdout.split():
        raise ValueError(f"use talosctl {talos_version}, matching the production template")
    results = []
    for role in (d for d in documents if d["kind"] in ("ControlPlane", "Workers")):
        name = role.get("name", "controlplane")
        machine_type = "controlplane" if role["kind"] == "ControlPlane" else "worker"
        folder = output / name
        folder.mkdir(mode=0o700)
        config_path = folder / "config.yaml"
        command = [binary, "gen", "config", "rebuild-validation", "https://192.0.2.1:6443",
                   "--talos-version", talos_version, "--kubernetes-version", kubernetes_version,
                   "--output-types", machine_type, "--output", str(config_path),
                   "--with-docs=false", "--with-examples=false"]
        for index, patch in enumerate(cluster.get("patches", []) + role.get("patches", [])):
            if patch.get("file") == PRIVATE_PATCH and not include_private:
                continue
            content = ((template.parent / patch["file"]).read_text() if "file" in patch
                       else yaml.safe_dump(patch["inline"]))
            patch_path = folder / f"patch-{index}.yaml"
            patch_path.write_text(content)
            command.extend(["--config-patch", "@" + str(patch_path)])
        generated = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (folder / "generation.log").write_text(generated.stdout + generated.stderr)
        result = {"role": name, "generate": generated.returncode, "validate": None, "errors": []}
        if generated.returncode == 0:
            checked = subprocess.run([binary, "validate", "--mode", "metal", "--config", str(config_path)],
                                     capture_output=True, text=True, timeout=60)
            (folder / "validation.log").write_text(checked.stdout + checked.stderr)
            result["validate"] = checked.returncode
            if checked.returncode == 0:
                result["errors"] = behavior_errors(list(yaml.safe_load_all(config_path.read_text())),
                                                   machine_type, kubernetes_version)
        results.append(result)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--talosctl", default="talosctl")
    parser.add_argument("--include-private-patches", action="store_true")
    parser.add_argument("--output-dir", type=Path, help="retain private configs/logs in a NEW directory")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.output_dir:
            args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
            results = validate(args.root, args.output_dir, args.include_private_patches, args.talosctl)
        else:
            with tempfile.TemporaryDirectory(prefix="omni-fresh-configs-") as folder:
                results = validate(args.root, Path(folder), args.include_private_patches, args.talosctl)
    except ValueError as error:
        print(f"FAIL: {error}")
        return 1
    except (OSError, yaml.YAMLError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("FAIL: could not validate fresh configurations; inspect inputs and retained private logs")
        return 1
    print(json.dumps(results, indent=2))
    print("Private registry patch: " + ("included" if args.include_private_patches else "skipped"))
    print("Offline generation only; VM installation and runtime storage/GPU behavior are not exercised.")
    return int(any(r["generate"] != 0 or r["validate"] != 0 or r["errors"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
