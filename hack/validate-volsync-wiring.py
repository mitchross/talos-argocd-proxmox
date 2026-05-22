#!/usr/bin/env python3
"""Render and validate VolSync PVC/ReplicationSource/ReplicationDestination wiring.

This script is intentionally repo-generic and read-only. It renders Kustomize
directories with `--enable-helm`, parses the rendered manifests, writes a DR
inventory table, and reports wiring failures that would break restore.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


ROOTS = ("infrastructure", "monitoring", "my-apps")
SOURCE_ROOTS = ("infrastructure", "my-apps")
VOLSYNC_API = "volsync.backube/v1alpha1"
VOLSYNC_GROUP = "volsync.backube"
SNAPSHOT_METHOD = "Snapshot"


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def kustomization_dirs(root: Path, paths: list[str] | None = None, excludes: list[str] | None = None) -> list[Path]:
    exclude_paths = [root / item for item in (excludes or [])]

    def included(path: Path) -> bool:
        return not any(path == excluded or excluded in path.parents for excluded in exclude_paths)

    if paths:
        return sorted((root / p).resolve() for p in paths if included((root / p).resolve()))
    dirs: list[Path] = []
    for base in ROOTS:
        base_path = root / base
        if not base_path.exists():
            continue
        for k in base_path.rglob("kustomization.yaml"):
            if "charts" in k.parts:
                continue
            directory = k.parent.resolve()
            if included(directory):
                dirs.append(directory)
    return sorted(set(dirs))


def render_path(root: Path, path: Path) -> tuple[list[dict[str, Any]], str | None]:
    proc = run(["kustomize", "build", str(path.relative_to(root)), "--enable-helm"], root)
    if proc.returncode != 0:
        return [], proc.stderr.strip() or proc.stdout.strip() or f"kustomize exited {proc.returncode}"
    docs: list[dict[str, Any]] = []
    try:
        for doc in yaml.safe_load_all(proc.stdout):
            if isinstance(doc, dict) and doc.get("kind"):
                doc["_renderPath"] = str(path.relative_to(root))
                docs.append(doc)
    except Exception as exc:  # pragma: no cover - defensive CLI guard
        return [], f"YAML parse failed: {exc}"
    return docs, None


def meta(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("metadata") or {}


def namespace(doc: dict[str, Any]) -> str:
    return meta(doc).get("namespace") or "default"


def name(doc: dict[str, Any]) -> str:
    return meta(doc).get("name") or ""


def annotations(doc: dict[str, Any]) -> dict[str, str]:
    return meta(doc).get("annotations") or {}


def sync_wave(doc: dict[str, Any]) -> str:
    return annotations(doc).get("argocd.argoproj.io/sync-wave", "")


def kopia(doc: dict[str, Any]) -> dict[str, Any]:
    return ((doc.get("spec") or {}).get("kopia") or {})


def pvc_data_source(doc: dict[str, Any]) -> dict[str, Any]:
    return ((doc.get("spec") or {}).get("dataSourceRef") or {})


def request_size(pvc: dict[str, Any]) -> str:
    return ((((pvc.get("spec") or {}).get("resources") or {}).get("requests") or {}).get("storage") or "")


def access_modes(doc: dict[str, Any]) -> list[str]:
    return list((doc.get("spec") or {}).get("accessModes") or [])


def mover_context(doc: dict[str, Any]) -> str:
    ctx = kopia(doc).get("moverSecurityContext") or {}
    return f"{ctx.get('runAsUser','')}/{ctx.get('runAsGroup','')}/{ctx.get('fsGroup','')}"


def trigger_summary(doc: dict[str, Any]) -> str:
    trig = (doc.get("spec") or {}).get("trigger") or {}
    if "schedule" in trig:
        return f"schedule: {trig['schedule']}"
    if "manual" in trig:
        return f"manual: {trig['manual']}"
    return ""


def workload_pvc_refs(doc: dict[str, Any]) -> list[str]:
    kind = doc.get("kind")
    specs: list[dict[str, Any]] = []
    if kind in {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"}:
        specs.append((((doc.get("spec") or {}).get("template") or {}).get("spec") or {}))
    elif kind in {"Job"}:
        specs.append((((doc.get("spec") or {}).get("template") or {}).get("spec") or {}))
    elif kind == "CronJob":
        specs.append((((((doc.get("spec") or {}).get("jobTemplate") or {}).get("spec") or {}).get("template") or {}).get("spec") or {}))
    elif kind == "Pod":
        specs.append(doc.get("spec") or {})

    refs: list[str] = []
    for spec in specs:
        for volume in spec.get("volumes") or []:
            claim = (volume.get("persistentVolumeClaim") or {}).get("claimName")
            if claim:
                refs.append(claim)
    return refs


def statefulset_claim_templates(doc: dict[str, Any]) -> list[str]:
    if doc.get("kind") != "StatefulSet":
        return []
    names: list[str] = []
    for tmpl in (doc.get("spec") or {}).get("volumeClaimTemplates") or []:
        tmpl_name = (tmpl.get("metadata") or {}).get("name")
        if tmpl_name:
            names.append(tmpl_name)
    return names


def secret_names_from_external_secret(doc: dict[str, Any]) -> set[str]:
    spec = doc.get("spec") or {}
    target = spec.get("target") or {}
    names = set()
    if target.get("name"):
        names.add(target["name"])
    if spec.get("externalSecretName"):
        names.add(spec["externalSecretName"])
    ext_spec = spec.get("externalSecretSpec") or {}
    ext_target = ext_spec.get("target") or {}
    if ext_target.get("name"):
        names.add(ext_target["name"])
    return names


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


@dataclass
class RenderResult:
    docs: list[dict[str, Any]] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)


def render_all(root: Path, paths: list[str] | None, excludes: list[str] | None = None) -> RenderResult:
    result = RenderResult()
    for path in kustomization_dirs(root, paths, excludes):
        docs, err = render_path(root, path)
        if err:
            result.failures[str(path.relative_to(root))] = err
        else:
            result.docs.extend(docs)
    return result


def build_indexes(docs: list[dict[str, Any]]) -> dict[str, Any]:
    idx: dict[str, Any] = {
        "pvcs": {},
        "rds": {},
        "rss": {},
        "secrets": defaultdict(set),
        "storageclasses": set(),
        "snapshotclasses": set(),
        "workloadRefs": defaultdict(list),
        "statefulTemplates": defaultdict(set),
        "renderPaths": defaultdict(set),
    }

    for doc in docs:
        key = (namespace(doc), name(doc))
        idx["renderPaths"][(doc.get("kind"), namespace(doc), name(doc))].add(doc.get("_renderPath", ""))
        kind = doc.get("kind")
        if kind == "PersistentVolumeClaim":
            idx["pvcs"][key] = doc
        elif kind == "ReplicationDestination" and doc.get("apiVersion") == VOLSYNC_API:
            idx["rds"][key] = doc
        elif kind == "ReplicationSource" and doc.get("apiVersion") == VOLSYNC_API:
            idx["rss"][key] = doc
        elif kind == "Secret":
            idx["secrets"][namespace(doc)].add(name(doc))
        elif kind in {"ExternalSecret", "ClusterExternalSecret"}:
            produced = secret_names_from_external_secret(doc)
            if kind == "ExternalSecret":
                idx["secrets"][namespace(doc)].update(produced)
            else:
                idx["secrets"]["*cluster*"].update(produced)
        elif kind == "StorageClass":
            idx["storageclasses"].add(name(doc))
        elif kind == "VolumeSnapshotClass":
            idx["snapshotclasses"].add(name(doc))

        for claim in workload_pvc_refs(doc):
            idx["workloadRefs"][(namespace(doc), claim)].append(f"{kind}/{name(doc)}")
        for tmpl in statefulset_claim_templates(doc):
            idx["statefulTemplates"][(namespace(doc), name(doc))].add(tmpl)

    return idx


def source_volsync_docs(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for base in SOURCE_ROOTS:
        base_path = root / base
        if not base_path.exists():
            continue
        for yaml_path in sorted(list(base_path.rglob("*.yaml")) + list(base_path.rglob("*.yml"))):
            if ".git" in yaml_path.parts:
                continue
            try:
                parsed = list(yaml.safe_load_all(yaml_path.read_text()))
            except Exception:
                continue
            for doc in parsed:
                if not isinstance(doc, dict):
                    continue
                if doc.get("apiVersion") == VOLSYNC_API and doc.get("kind") in {"ReplicationSource", "ReplicationDestination"}:
                    doc["_sourcePath"] = str(yaml_path.relative_to(root))
                    docs.append(doc)
    return docs


def inactive_source_volsync_docs(source_docs: list[dict[str, Any]], idx: dict[str, Any]) -> list[str]:
    inactive: list[str] = []
    rendered = {
        ("ReplicationSource", ns, resource_name)
        for (ns, resource_name) in idx["rss"].keys()
    }
    rendered.update(
        {
            ("ReplicationDestination", ns, resource_name)
            for (ns, resource_name) in idx["rds"].keys()
        }
    )

    for doc in source_docs:
        key = (doc.get("kind"), namespace(doc), name(doc))
        if key not in rendered:
            inactive.append(f"{doc['_sourcePath']}: {key[1]}/{key[0]}/{key[2]} is present in source but not rendered by active kustomizations")
    return inactive


def inventory_rows(idx: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    backed_pvcs = []
    for key, pvc in idx["pvcs"].items():
        ds = pvc_data_source(pvc)
        if ds.get("kind") == "ReplicationDestination":
            backed_pvcs.append((key, pvc))
    backed_pvcs.sort()

    for (ns, pvc_name), pvc in backed_pvcs:
        ds = pvc_data_source(pvc)
        rd = idx["rds"].get((ns, ds.get("name")))
        rs = idx["rss"].get((ns, pvc_name))
        pvc_spec = pvc.get("spec") or {}
        rd_kopia = kopia(rd or {})
        rs_kopia = kopia(rs or {})
        workloads = idx["workloadRefs"].get((ns, pvc_name), [])
        rows.append(
            {
                "namespace": ns,
                "app/path": ", ".join(sorted(idx["renderPaths"].get(("PersistentVolumeClaim", ns, pvc_name), []))),
                "PVC": pvc_name,
                "PVC storageClass": pvc_spec.get("storageClassName", ""),
                "PVC size": request_size(pvc),
                "PVC accessModes": ",".join(access_modes(pvc)),
                "dataSourceRef": f"{ds.get('apiGroup','')}/{ds.get('kind','')}/{ds.get('name','')}",
                "RD": name(rd or {}),
                "RD copyMethod": rd_kopia.get("copyMethod", ""),
                "RD capacity": rd_kopia.get("capacity", ""),
                "RD storageClass": rd_kopia.get("storageClassName", ""),
                "RD snapshotClass": rd_kopia.get("volumeSnapshotClassName", ""),
                "RD repo": rd_kopia.get("repository", ""),
                "RD mover UID/GID/fsGroup": mover_context(rd or {}),
                "RS": name(rs or {}),
                "RS sourcePVC": ((rs or {}).get("spec") or {}).get("sourcePVC", ""),
                "RS trigger": trigger_summary(rs or {}),
                "RS copyMethod": rs_kopia.get("copyMethod", ""),
                "RS repo": rs_kopia.get("repository", ""),
                "RS mover UID/GID/fsGroup": mover_context(rs or {}),
                "retention": json.dumps(rs_kopia.get("retain", {}), sort_keys=True),
                "sync waves": f"pvc={sync_wave(pvc)} rd={sync_wave(rd or {})} rs={sync_wave(rs or {})}",
                "workloads": ", ".join(sorted(workloads)),
                "app PVC count": "",
            }
        )

    by_path: dict[str, int] = defaultdict(int)
    for row in rows:
        by_path[row["app/path"]] += 1
    for row in rows:
        count = by_path[row["app/path"]]
        row["app PVC count"] = "multi" if count > 1 else "single"
    return rows


SSDIFF_OFF_TOKEN = "ServerSideDiff=false"
COMPARE_OPTIONS_KEY = "argocd.argoproj.io/compare-options"


def pvc_has_ssdiff_shim(pvc: dict[str, Any]) -> bool:
    """True if the rendered PVC carries the `ServerSideDiff=false` shim that
    keeps Argo CD's server-side diff dry-run from rejecting an immutable
    dataSourceRef on a Bound PVC. The annotation may live directly on the PVC
    (set in the source YAML or by a Kustomize JSONPatch) and is preserved by
    the AppSet-level `ignoreApplicationDifferences` shim for compare-options.
    See docs/argocd.md "Server-Side Diff & Apply Strategy"."""
    value = annotations(pvc).get(COMPARE_OPTIONS_KEY, "")
    return SSDIFF_OFF_TOKEN in value


def validate(idx: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    cluster_secret_names = idx["secrets"].get("*cluster*", set())

    for row in rows:
        ns = row["namespace"]
        pvc_name = row["PVC"]
        pvc = idx["pvcs"][(ns, pvc_name)]
        ds = pvc_data_source(pvc)
        rd_name = ds.get("name")
        rd = idx["rds"].get((ns, rd_name))
        rs = idx["rss"].get((ns, pvc_name))

        if ds.get("apiGroup") != VOLSYNC_GROUP:
            failures.append(f"{ns}/{pvc_name}: dataSourceRef apiGroup is {ds.get('apiGroup')}, expected {VOLSYNC_GROUP}")
        if not pvc_has_ssdiff_shim(pvc):
            failures.append(
                f"{ns}/{pvc_name}: PVC with static dataSourceRef is missing "
                f"{COMPARE_OPTIONS_KEY}: ServerSideDiff=false. Without it, "
                f"Argo CD's global server-side diff dry-runs SSA and the "
                f"apiserver rejects the change to immutable dataSourceRef, "
                f"wedging the whole app's sync. Add the annotation directly "
                f"to the PVC manifest (single-YAML apps) or via a Kustomize "
                f"JSONPatch (chart-rendered PVCs like gitea). See "
                f"docs/argocd.md 'Server-Side Diff & Apply Strategy'."
            )
        if not rd:
            failures.append(f"{ns}/{pvc_name}: missing ReplicationDestination {rd_name}")
        if not rs:
            failures.append(f"{ns}/{pvc_name}: missing ReplicationSource named {pvc_name}")
        if rd:
            rd_kopia = kopia(rd)
            if rd_kopia.get("copyMethod") != SNAPSHOT_METHOD:
                failures.append(f"{ns}/{rd_name}: RD copyMethod is {rd_kopia.get('copyMethod')}, expected Snapshot")
            if rd_kopia.get("capacity") != request_size(pvc):
                failures.append(f"{ns}/{pvc_name}: PVC size {request_size(pvc)} != RD capacity {rd_kopia.get('capacity')}")
            if rd_kopia.get("storageClassName") != (pvc.get("spec") or {}).get("storageClassName"):
                failures.append(f"{ns}/{pvc_name}: PVC storageClass {(pvc.get('spec') or {}).get('storageClassName')} != RD storageClass {rd_kopia.get('storageClassName')}")
            if access_modes(pvc) != list(rd_kopia.get("accessModes") or []):
                failures.append(f"{ns}/{pvc_name}: PVC accessModes {access_modes(pvc)} != RD accessModes {rd_kopia.get('accessModes')}")
            if not rd_kopia.get("moverSecurityContext"):
                failures.append(f"{ns}/{rd_name}: RD missing moverSecurityContext")
            if rd_kopia.get("repository") not in idx["secrets"].get(ns, set()) and rd_kopia.get("repository") not in cluster_secret_names:
                failures.append(f"{ns}/{rd_name}: RD repository secret {rd_kopia.get('repository')} is not rendered by Secret/ExternalSecret/ClusterExternalSecret")
        if rs:
            rs_spec = rs.get("spec") or {}
            rs_kopia = kopia(rs)
            if rs_spec.get("sourcePVC") != pvc_name:
                failures.append(f"{ns}/{name(rs)}: RS sourcePVC {rs_spec.get('sourcePVC')} != {pvc_name}")
            if rs_kopia.get("copyMethod") != SNAPSHOT_METHOD:
                failures.append(f"{ns}/{name(rs)}: RS copyMethod is {rs_kopia.get('copyMethod')}, expected Snapshot")
            if not ((rs_spec.get("trigger") or {}).get("schedule") or (rs_spec.get("trigger") or {}).get("manual")):
                failures.append(f"{ns}/{name(rs)}: RS missing trigger schedule/manual")
            if not rs_kopia.get("moverSecurityContext"):
                failures.append(f"{ns}/{name(rs)}: RS missing moverSecurityContext")
            if rs_kopia.get("repository") not in idx["secrets"].get(ns, set()) and rs_kopia.get("repository") not in cluster_secret_names:
                failures.append(f"{ns}/{name(rs)}: RS repository secret {rs_kopia.get('repository')} is not rendered by Secret/ExternalSecret/ClusterExternalSecret")
            snap = rs_kopia.get("volumeSnapshotClassName")
            if snap and snap not in idx["snapshotclasses"]:
                failures.append(f"{ns}/{name(rs)}: RS snapshot class {snap} not rendered by repo")

    # Orphaned RS/RD checks.
    pvc_keys = set(idx["pvcs"].keys())
    for (ns, rs_name), rs in sorted(idx["rss"].items()):
        source = ((rs.get("spec") or {}).get("sourcePVC"))
        if (ns, source) not in pvc_keys:
            failures.append(f"{ns}/{rs_name}: RS sourcePVC {source} has no rendered PVC")
    for (ns, rd_name), rd in sorted(idx["rds"].items()):
        rd_kopia = kopia(rd)
        if rd_kopia.get("copyMethod") == SNAPSHOT_METHOD and not rd_kopia.get("capacity"):
            failures.append(f"{ns}/{rd_name}: RD Snapshot restore missing capacity")
        if not rd_kopia.get("accessModes"):
            failures.append(f"{ns}/{rd_name}: RD missing accessModes")
        if not rd_kopia.get("storageClassName"):
            failures.append(f"{ns}/{rd_name}: RD missing storageClassName")

    # Workload references must resolve to a rendered PVC or a StatefulSet claim template.
    for (ns, claim), owners in sorted(idx["workloadRefs"].items()):
        if (ns, claim) in idx["pvcs"]:
            continue
        templated = any(claim in templates for (tmpl_ns, _), templates in idx["statefulTemplates"].items() if tmpl_ns == ns)
        if not templated:
            failures.append(f"{ns}/{claim}: workload claim reference used by {', '.join(owners)} has no rendered PVC or StatefulSet volumeClaimTemplate")

    schedules = [row["RS trigger"].replace("schedule: ", "") for row in rows if row["RS trigger"].startswith("schedule: ")]
    if schedules and len(set(schedules)) == 1:
        failures.append(f"all ReplicationSource schedules are identical: {schedules[0]}")

    return failures


def write_inventory(
    path: Path,
    rows: list[dict[str, Any]],
    render_failures: dict[str, str],
    failures: list[str],
    inactive_source_docs: list[str],
) -> None:
    headers = [
        "namespace",
        "app/path",
        "PVC",
        "PVC storageClass",
        "PVC size",
        "PVC accessModes",
        "dataSourceRef",
        "RD",
        "RD capacity",
        "RD repo",
        "RS",
        "RS trigger",
        "RS repo",
        "mover UID/GID/fsGroup",
        "retention",
        "workloads",
        "app PVC count",
    ]
    lines = [
        "# VolSync DR Inventory",
        "",
        "Generated by `hack/validate-volsync-wiring.py` from rendered Kustomize manifests.",
        "",
        f"- Render failures: {len(render_failures)}",
        f"- Wiring failures: {len(failures)}",
        f"- Inactive source VolSync docs: {len(inactive_source_docs)}",
        f"- Backed-up PVCs: {len(rows)}",
        "",
    ]
    if render_failures:
        lines += ["## Render Failures", ""]
        for render_path, err in sorted(render_failures.items()):
            lines += [f"- `{render_path}`: `{err.splitlines()[0] if err else 'failed'}`"]
        lines += [""]
    if failures:
        lines += ["## Wiring Failures", ""]
        lines += [f"- {failure}" for failure in failures]
        lines += [""]
    if inactive_source_docs:
        lines += ["## Inactive Source VolSync Docs", ""]
        lines += [f"- {doc}" for doc in inactive_source_docs]
        lines += [""]
    lines += ["## Inventory", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        values = []
        for header in headers:
            if header == "mover UID/GID/fsGroup":
                value = f"rs={row['RS mover UID/GID/fsGroup']} rd={row['RD mover UID/GID/fsGroup']}"
            else:
                value = row.get(header, "")
            values.append(md_escape(value))
        lines.append("| " + " | ".join(values) + " |")
    lines.append("")
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".", help="repository root")
    parser.add_argument("--path", action="append", help="render only this kustomization directory, repeatable")
    parser.add_argument("--exclude", action="append", default=[], help="skip this kustomization path prefix, repeatable")
    parser.add_argument("--inventory", default="docs/volsync-dr-inventory.md", help="markdown inventory output")
    parser.add_argument("--json", default="", help="optional JSON summary output")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    render = render_all(root, args.path, args.exclude)
    idx = build_indexes(render.docs)
    rows = inventory_rows(idx)
    failures = validate(idx, rows)
    inactive = inactive_source_volsync_docs(source_volsync_docs(root), idx)
    write_inventory(root / args.inventory, rows, render.failures, failures, inactive)

    summary = {
        "rendered_documents": len(render.docs),
        "render_failures": render.failures,
        "backed_up_pvcs": len(rows),
        "wiring_failures": failures,
        "inactive_source_volsync_docs": inactive,
        "inventory": args.inventory,
    }
    if args.json:
        (root / args.json).write_text(json.dumps(summary, indent=2, sort_keys=True))

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if render.failures or failures or inactive else 0


if __name__ == "__main__":
    sys.exit(main())
