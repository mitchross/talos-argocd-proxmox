#!/usr/bin/env python3
"""hack/pvc-plumber-inventory.py — pvc-plumber v4 Phase 1 inventory generator.

Read-only static analysis of the talos-argocd-proxmox repo, plus an optional
read-only cluster cross-reference. Renders Kustomize directories with
`--enable-helm` so Helm-rendered PVCs (gitea, n8n, posthog data layer, temporal)
are expanded the same way Argo CD does it.

For every protected PVC, emits one row to docs/pvc-plumber-v4-inventory.md with
the columns Phase 1 requires (namespace, app path, PVC name, workload claim
references, storageClass, size, accessModes, current dataSourceRef, expected
and current RS/RD names, repository secret reference, backup identity,
mover UID/GID/fsGroup, schedule/tier, restore-policy/mode, owner
classification, migration recommendation).

Each PVC is classified into one of:

  - inline-argo:    PVC + RS + RD all rendered from Git (current pattern).
  - orphan-cluster: RS/RD exists in cluster only, not in Git (deleted-operator
                    era). Requires --with-cluster for authoritative detection;
                    static analysis can only mark a PVC as suspect-orphan.
  - helm-rendered:  PVC manifest is produced by a Helm chart inflation. May
                    or may not have an inline dataSourceRef + RS/RD wired.
  - backup-exempt:  Labeled backup-exempt: "true". FQ reason annotation
                    storage.vanillax.dev/backup-exempt-reason is required.
  - cnpg-excluded:  CNPG database PVC. Backed up via Barman → S3, not VolSync.
  - unknown:        Needs human review before any phase.

NEVER mutates state. NEVER applies. NEVER deletes. The optional cluster query
uses only `kubectl get ... -o json` against the user's current kubectl context.

Phase 1 of docs/pvc-plumber-v4-prd.md. Inventory is the gate before any
operator-repo code (Phase 2) or talos-repo manifest (Phase 3) work begins.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# Directories to scan for kustomizations. We do NOT scan monitoring/ — those
# PVCs are Prometheus/Loki/Grafana and use storage classes without snapshot
# support, plus they're explicitly excluded from the backup contract.
SCAN_ROOTS = ("my-apps", "infrastructure")

# Directories to exclude from scanning. CNPG databases use Barman → S3 and are
# explicitly excluded from VolSync (see CLAUDE.md). Other excludes are either
# operator-only (no PVCs) or shared kustomize components.
EXCLUDE_DIRS = (
    "infrastructure/database/cloudnative-pg",   # CNPG instances — Barman, not VolSync
    "infrastructure/database/cnpg-barman-plugin",  # CNPG plugin operator
    "infrastructure/database/crunchy-postgres",  # Crunchy operator only
    "infrastructure/storage/container-registry",  # kube-system PVC, explicitly excluded
    "infrastructure/controllers",                 # operators, no application PVCs
    "infrastructure/networking",                  # no PVCs
    "infrastructure/storage/volsync",             # operator install
    "infrastructure/storage/volsync-backup-cluster",  # MAP + ClusterES, no PVCs
    "infrastructure/storage/longhorn",            # storage operator
    "infrastructure/storage/snapshot-controller",
    "infrastructure/storage/csi-driver-nfs",
    "infrastructure/storage/csi-driver-smb",
    "infrastructure/storage/local-storage",
    "infrastructure/storage/kopia-ui",             # admin tool, no protected PVC
    "infrastructure/storage/rustfs-lifecycle",     # bucket lifecycle config
    "my-apps/common",                              # shared kustomize components
)

# Namespaces that must NEVER receive backup labels. Per CLAUDE.md DON'T list.
SYSTEM_NAMESPACES = frozenset({
    "kube-system",
    "volsync-system",
    "argocd",
    "longhorn-system",
    "cert-manager",
    "external-secrets",
    "1passwordconnect",
    "snapshot-controller",
    "kyverno",
    "gpu-operator",
    "node-feature-discovery",
    "metrics-server",
    "external-dns",
})

VOLSYNC_API = "volsync.backube/v1alpha1"
VOLSYNC_GROUP = "volsync.backube"

# Label / annotation keys from CLAUDE.md and the v4 PRD.
LABEL_BACKUP_EXEMPT = "backup-exempt"
ANN_BACKUP_EXEMPT_REASON_FQ = "storage.vanillax.dev/backup-exempt-reason"
ANN_BACKUP_EXEMPT_REASON_BARE = "backup-exempt-reason"  # the silent-fail landmine
LABEL_RESTORE_POLICY = "restore-policy"
LABEL_PVC_PLUMBER_ENABLED = "pvc-plumber.io/enabled"
LABEL_PVC_PLUMBER_TIER = "pvc-plumber.io/tier"
LABEL_LEGACY_BACKUP = "backup"  # values: hourly|daily — dead, but report anyway
ANN_PVC_PLUMBER_UID = "pvc-plumber.io/uid"
ANN_PVC_PLUMBER_GID = "pvc-plumber.io/gid"
ANN_PVC_PLUMBER_MODE = "pvc-plumber.io/mode"
ANN_PVC_PLUMBER_RESTORE_MODE = "pvc-plumber.io/restore-mode"
ANN_PVC_PLUMBER_BACKUP_IDENTITY = "pvc-plumber.io/backup-identity"
ANN_ARGOCD_COMPARE_OPTIONS = "argocd.argoproj.io/compare-options"
NAMESPACE_PRIVILEGED_MOVERS_LABEL = "volsync.backube/privileged-movers"

# The shared kopia repo Secret, materialized by ClusterExternalSecret.
SHARED_REPO_SECRET = "volsync-kopia-repository"

# Owner classification buckets (ordered for stable report sections).
CLASSIFICATIONS = (
    "inline-argo",
    "helm-rendered",
    "orphan-cluster",
    "backup-exempt",
    "cnpg-excluded",
    "unknown",
)


# ---------------------------------------------------------------------------
# Kustomize rendering — re-uses the same approach as
# hack/validate-volsync-wiring.py for consistency. Read-only.
# ---------------------------------------------------------------------------


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def kustomization_dirs(root: Path, excludes: tuple[str, ...]) -> list[Path]:
    exclude_paths = [root / item for item in excludes]

    def included(path: Path) -> bool:
        return not any(path == excluded or excluded in path.parents for excluded in exclude_paths)

    dirs: list[Path] = []
    for base in SCAN_ROOTS:
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
        return [], (proc.stderr.strip() or proc.stdout.strip() or f"kustomize exited {proc.returncode}")
    docs: list[dict[str, Any]] = []
    try:
        for doc in yaml.safe_load_all(proc.stdout):
            if isinstance(doc, dict) and doc.get("kind"):
                doc["_renderPath"] = str(path.relative_to(root))
                docs.append(doc)
    except Exception as exc:
        return [], f"YAML parse failed: {exc}"
    return docs, None


def kustomization_uses_helm(path: Path) -> bool:
    """True if the directory's kustomization.yaml has a helmCharts: block."""
    k = path / "kustomization.yaml"
    if not k.exists():
        return False
    try:
        data = yaml.safe_load(k.read_text())
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return bool(data.get("helmCharts"))


# ---------------------------------------------------------------------------
# Doc helpers.
# ---------------------------------------------------------------------------


def meta(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("metadata") or {}


def name(doc: dict[str, Any]) -> str:
    return meta(doc).get("name") or ""


def namespace(doc: dict[str, Any]) -> str:
    return meta(doc).get("namespace") or ""


def labels(doc: dict[str, Any]) -> dict[str, str]:
    return meta(doc).get("labels") or {}


def annotations(doc: dict[str, Any]) -> dict[str, str]:
    return meta(doc).get("annotations") or {}


def spec(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("spec") or {}


def kopia(doc: dict[str, Any]) -> dict[str, Any]:
    return spec(doc).get("kopia") or {}


def pvc_data_source_ref(pvc: dict[str, Any]) -> dict[str, Any]:
    return spec(pvc).get("dataSourceRef") or {}


def pvc_request_size(pvc: dict[str, Any]) -> str:
    return (((spec(pvc).get("resources") or {}).get("requests") or {}).get("storage")) or ""


def pvc_access_modes(pvc: dict[str, Any]) -> list[str]:
    return list(spec(pvc).get("accessModes") or [])


def is_helm_rendered(doc: dict[str, Any]) -> bool:
    lbls = labels(doc)
    if lbls.get("app.kubernetes.io/managed-by", "").lower() == "helm":
        return True
    if any(key.startswith("helm.sh/") for key in lbls):
        return True
    if any(key.startswith("helm.sh/") for key in annotations(doc)):
        return True
    return False


def workload_pvc_refs(doc: dict[str, Any]) -> list[str]:
    """Return PVC names that this workload mounts via persistentVolumeClaim.claimName."""
    kind = doc.get("kind")
    specs: list[dict[str, Any]] = []
    if kind in {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"}:
        specs.append(((spec(doc).get("template") or {}).get("spec") or {}))
    elif kind == "CronJob":
        specs.append(((((spec(doc).get("jobTemplate") or {}).get("spec") or {}).get("template") or {}).get("spec") or {}))
    elif kind == "Pod":
        specs.append(spec(doc))
    refs: list[str] = []
    for pod_spec in specs:
        for volume in pod_spec.get("volumes") or []:
            claim = (volume.get("persistentVolumeClaim") or {}).get("claimName")
            if claim:
                refs.append(claim)
    return refs


def statefulset_claim_templates(doc: dict[str, Any]) -> list[str]:
    if doc.get("kind") != "StatefulSet":
        return []
    names: list[str] = []
    for tmpl in spec(doc).get("volumeClaimTemplates") or []:
        tmpl_name = (tmpl.get("metadata") or {}).get("name")
        if tmpl_name:
            names.append(tmpl_name)
    return names


# ---------------------------------------------------------------------------
# Schedule → tier inference.
# ---------------------------------------------------------------------------


_CRON_FIELD_RE = re.compile(r"\S+")


def classify_schedule(schedule: str) -> str:
    """Best-effort mapping from cron string → tier label."""
    if not schedule:
        return ""
    parts = _CRON_FIELD_RE.findall(schedule)
    if len(parts) != 5:
        return f"unknown-cron({schedule})"
    minute, hour, dom, month, dow = parts
    # Weekly: day-of-week pinned to a single value.
    if dow not in ("*", "?") and "," not in dow and "/" not in dow:
        return "weekly"
    # Daily: specific hour, any day.
    if hour != "*" and dom == "*" and month == "*" and (dow in ("*", "?")):
        return "daily"
    # Hourly: minute pinned, hour wildcard.
    if hour == "*" and dom == "*" and month == "*" and (dow in ("*", "?")):
        return "hourly"
    return f"custom({schedule})"


# ---------------------------------------------------------------------------
# Index + classification.
# ---------------------------------------------------------------------------


@dataclass
class Index:
    pvcs: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    rss: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    rds: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    secrets: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    cluster_es_secrets: set[str] = field(default_factory=set)
    namespaces: dict[str, dict[str, Any]] = field(default_factory=dict)  # ns → Namespace doc
    workload_refs: dict[tuple[str, str], list[str]] = field(default_factory=lambda: defaultdict(list))
    stateful_templates: dict[tuple[str, str], set[str]] = field(default_factory=lambda: defaultdict(set))
    render_paths: dict[tuple[str, str, str], set[str]] = field(default_factory=lambda: defaultdict(set))
    helm_dirs: set[str] = field(default_factory=set)  # render-path strings whose kustomization uses helmCharts:


def build_index(docs: list[dict[str, Any]], helm_dirs: set[str]) -> Index:
    idx = Index()
    idx.helm_dirs = helm_dirs
    for doc in docs:
        kind = doc.get("kind")
        ns = namespace(doc)
        nm = name(doc)
        key = (ns, nm)
        idx.render_paths[(kind or "", ns, nm)].add(doc.get("_renderPath", ""))
        if kind == "PersistentVolumeClaim":
            idx.pvcs[key] = doc
        elif kind == "ReplicationSource" and doc.get("apiVersion") == VOLSYNC_API:
            idx.rss[key] = doc
        elif kind == "ReplicationDestination" and doc.get("apiVersion") == VOLSYNC_API:
            idx.rds[key] = doc
        elif kind == "Secret":
            idx.secrets[ns].add(nm)
        elif kind == "ExternalSecret":
            target = spec(doc).get("target") or {}
            if target.get("name"):
                idx.secrets[ns].add(target["name"])
        elif kind == "ClusterExternalSecret":
            # Per cluster ES, the target secret is populated in any namespace
            # matching the namespaceSelector. We treat the targetName as
            # available in any non-system namespace that has the selector
            # label; the precise selector-walking is done in classify().
            ext_spec = spec(doc).get("externalSecretSpec") or {}
            ext_target = ext_spec.get("target") or {}
            if ext_target.get("name"):
                idx.cluster_es_secrets.add(ext_target["name"])
        elif kind == "Namespace":
            idx.namespaces[nm] = doc

        for claim in workload_pvc_refs(doc):
            idx.workload_refs[(ns, claim)].append(f"{kind}/{nm}")
        for tmpl in statefulset_claim_templates(doc):
            idx.stateful_templates[(ns, nm)].add(tmpl)
    return idx


# ---------------------------------------------------------------------------
# Cluster cross-reference (optional, read-only).
# ---------------------------------------------------------------------------


@dataclass
class ClusterState:
    rss: set[tuple[str, str]] = field(default_factory=set)  # (namespace, name)
    rds: set[tuple[str, str]] = field(default_factory=set)
    rss_by_pvc: dict[tuple[str, str], str] = field(default_factory=dict)  # (ns, sourcePVC) → RS name
    rds_managed_by: dict[tuple[str, str], str] = field(default_factory=dict)
    rss_managed_by: dict[tuple[str, str], str] = field(default_factory=dict)
    error: str | None = None


def query_cluster() -> ClusterState:
    state = ClusterState()
    for kind in ("replicationsources.volsync.backube", "replicationdestinations.volsync.backube"):
        proc = subprocess.run(
            ["kubectl", "get", kind, "-A", "-o", "json"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            state.error = f"kubectl get {kind} failed: {proc.stderr.strip()}"
            return state
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            state.error = f"kubectl get {kind} JSON parse failed: {exc}"
            return state
        for item in data.get("items", []):
            ns = (item.get("metadata") or {}).get("namespace") or ""
            nm = (item.get("metadata") or {}).get("name") or ""
            mgr = ((item.get("metadata") or {}).get("labels") or {}).get("app.kubernetes.io/managed-by", "")
            if kind.startswith("replicationsources"):
                state.rss.add((ns, nm))
                state.rss_managed_by[(ns, nm)] = mgr
                source_pvc = ((item.get("spec") or {}).get("sourcePVC")) or ""
                if source_pvc:
                    state.rss_by_pvc[(ns, source_pvc)] = nm
            else:
                state.rds.add((ns, nm))
                state.rds_managed_by[(ns, nm)] = mgr
    return state


# ---------------------------------------------------------------------------
# Per-PVC row builder.
# ---------------------------------------------------------------------------


@dataclass
class PVCRow:
    namespace: str
    app_path: str
    pvc_name: str
    workload_claim_refs: list[str]
    storage_class: str
    requested_size: str
    access_modes: list[str]
    current_data_source_ref: str
    expected_rd: str
    current_rd: str
    expected_rs: str
    current_rs: str
    repo_secret_ref: str
    backup_identity: str
    mover_uid: str
    mover_gid: str
    mover_fsgroup: str
    schedule: str
    tier: str
    restore_policy: str
    pvc_plumber_enabled: bool
    pvc_plumber_tier: str
    pvc_plumber_mode: str
    classification: str
    migration_recommendation: str
    blockers: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "app/path": self.app_path,
            "pvc": self.pvc_name,
            "workload claimName refs": ", ".join(self.workload_claim_refs),
            "storageClass": self.storage_class,
            "size": self.requested_size,
            "accessModes": ",".join(self.access_modes),
            "current dataSourceRef": self.current_data_source_ref,
            "expected RD": self.expected_rd,
            "current RD": self.current_rd,
            "expected RS": self.expected_rs,
            "current RS": self.current_rs,
            "repo secret / ClusterES": self.repo_secret_ref,
            "backup identity": self.backup_identity,
            "mover UID": self.mover_uid,
            "mover GID": self.mover_gid,
            "mover fsGroup": self.mover_fsgroup,
            "schedule": self.schedule,
            "tier": self.tier,
            "restore-policy / mode": self.restore_policy,
            "pvc-plumber.io/enabled": "yes" if self.pvc_plumber_enabled else "",
            "pvc-plumber.io/tier": self.pvc_plumber_tier,
            "pvc-plumber.io/mode": self.pvc_plumber_mode,
            "classification": self.classification,
            "migration recommendation": self.migration_recommendation,
            "blockers": "; ".join(self.blockers),
            "notes": "; ".join(self.notes),
        }


def build_row(
    pvc: dict[str, Any],
    idx: Index,
    cluster: ClusterState | None,
    render_paths_for_pvc: set[str],
) -> PVCRow:
    ns = namespace(pvc)
    nm = name(pvc)
    expected_rd = f"{nm}-dst"
    expected_rs = nm

    lbls = labels(pvc)
    anns = annotations(pvc)
    pvc_spec = spec(pvc)

    data_source_ref = pvc_data_source_ref(pvc)
    ds_str = ""
    if data_source_ref.get("kind"):
        ds_str = f"{data_source_ref.get('apiGroup','')}/{data_source_ref.get('kind','')}/{data_source_ref.get('name','')}"

    rd_doc = idx.rds.get((ns, expected_rd)) or idx.rds.get((ns, data_source_ref.get("name") or ""))
    rs_doc = idx.rss.get((ns, expected_rs))

    # Mover security context — prefer RS, fall back to RD.
    mover_ctx = (kopia(rs_doc or {}).get("moverSecurityContext")
                 or kopia(rd_doc or {}).get("moverSecurityContext")
                 or {})
    mover_uid = str(mover_ctx.get("runAsUser", "") or "")
    mover_gid = str(mover_ctx.get("runAsGroup", "") or "")
    mover_fsgroup = str(mover_ctx.get("fsGroup", "") or "")

    schedule = ""
    if rs_doc:
        schedule = ((spec(rs_doc).get("trigger") or {}).get("schedule")) or ""
    tier = classify_schedule(schedule)

    restore_policy = lbls.get(LABEL_RESTORE_POLICY, "")
    pvc_plumber_tier = lbls.get(LABEL_PVC_PLUMBER_TIER, "")
    pvc_plumber_mode = anns.get(ANN_PVC_PLUMBER_MODE, "")
    pvc_plumber_enabled = lbls.get(LABEL_PVC_PLUMBER_ENABLED, "").lower() in ("true", "1", "yes")
    legacy_backup_tier = lbls.get(LABEL_LEGACY_BACKUP, "")

    repo_secret = ""
    if rs_doc:
        repo_secret = kopia(rs_doc).get("repository", "")
    elif rd_doc:
        repo_secret = kopia(rd_doc).get("repository", "")
    if not repo_secret and SHARED_REPO_SECRET in idx.cluster_es_secrets:
        repo_secret = f"(ClusterES: {SHARED_REPO_SECRET})"

    identity_override = anns.get(ANN_PVC_PLUMBER_BACKUP_IDENTITY, "")
    backup_identity = identity_override or f"{ns}/{nm}"

    workload_refs = sorted(set(idx.workload_refs.get((ns, nm), [])))

    blockers: list[str] = []
    notes: list[str] = []

    # Backup-exempt detection.
    exempt = lbls.get(LABEL_BACKUP_EXEMPT, "").lower() in ("true", "1", "yes")
    exempt_reason_fq = anns.get(ANN_BACKUP_EXEMPT_REASON_FQ, "")
    exempt_reason_bare = anns.get(ANN_BACKUP_EXEMPT_REASON_BARE, "")

    # CNPG detection (Helm-rendered CNPG cluster PVCs slip in if scanning catches them).
    cnpg_excluded = (
        "cloudnative-pg" in ns
        or any("cloudnative-pg" in rp for rp in render_paths_for_pvc)
        or lbls.get("cnpg.io/cluster") is not None
    )

    # Helm-rendered detection.
    helm_rendered = (
        is_helm_rendered(pvc)
        or any(rp in idx.helm_dirs for rp in render_paths_for_pvc)
    )

    # System-namespace exclusion (these should never appear here, but guard anyway).
    if ns in SYSTEM_NAMESPACES:
        notes.append(f"system namespace {ns} — should not be in inventory; investigate")

    has_dsr = bool(data_source_ref.get("kind") == "ReplicationDestination")
    has_rd = rd_doc is not None
    has_rs = rs_doc is not None
    has_inline_wiring = has_dsr and has_rd and has_rs

    classification = "unknown"
    if cnpg_excluded:
        classification = "cnpg-excluded"
    elif exempt:
        classification = "backup-exempt"
        if not exempt_reason_fq:
            if exempt_reason_bare:
                blockers.append(
                    f"backup-exempt label present, but reason is on the BARE key "
                    f"({ANN_BACKUP_EXEMPT_REASON_BARE}). The FQ key "
                    f"({ANN_BACKUP_EXEMPT_REASON_FQ}) is required — "
                    f"bare key is silently ignored; CI `backup-exempt-contract` enforces FQ."
                )
            else:
                blockers.append(
                    f"backup-exempt label present without any reason annotation. "
                    f"Require {ANN_BACKUP_EXEMPT_REASON_FQ}: \"<reason>\"."
                )
    elif helm_rendered:
        classification = "helm-rendered"
    elif has_inline_wiring:
        classification = "inline-argo"
    else:
        classification = "unknown"

    # Cluster cross-reference promotes unknown → orphan-cluster when RS or RD exists in cluster but not in Git.
    if cluster is not None and classification == "unknown":
        has_cluster_rs = (ns, expected_rs) in cluster.rss or (ns, nm) in cluster.rss_by_pvc
        has_cluster_rd = (ns, expected_rd) in cluster.rds or any(
            (ns, candidate) in cluster.rds for candidate in (f"{nm}-backup", f"{nm}-dst", nm)
        )
        if has_cluster_rs or has_cluster_rd:
            classification = "orphan-cluster"

    if cluster is not None and classification in ("inline-argo", "helm-rendered"):
        # Even for inline apps, if there are extra cluster RS/RD beyond what Git renders,
        # surface as a note.
        legacy_rs = (ns, f"{nm}-backup") in cluster.rss
        legacy_rd = (ns, f"{nm}-backup") in cluster.rds
        if legacy_rs or legacy_rd:
            notes.append(
                f"cluster also has legacy pvc-plumber-era resources "
                f"({nm}-backup); not in Git — cleanup or adopt during Phase 6."
            )

    # Wiring sanity checks within Git for inline-argo and helm-rendered.
    if classification in ("inline-argo", "helm-rendered"):
        if not has_dsr:
            blockers.append("PVC has no dataSourceRef → restore-on-recreate will bind empty.")
        if not has_rd:
            blockers.append(f"PVC has dataSourceRef but rendered RD '{expected_rd}' is missing.")
        if not has_rs:
            blockers.append(f"PVC has no rendered RS '{expected_rs}' — backups will not run.")
        if has_dsr and data_source_ref.get("apiGroup") != VOLSYNC_GROUP:
            blockers.append(
                f"dataSourceRef apiGroup is '{data_source_ref.get('apiGroup','')}', "
                f"expected '{VOLSYNC_GROUP}'."
            )
        # ServerSideDiff shim check.
        cmp_opts = anns.get(ANN_ARGOCD_COMPARE_OPTIONS, "")
        if has_dsr and "ServerSideDiff=false" not in cmp_opts:
            blockers.append(
                f"PVC with static dataSourceRef missing "
                f"`{ANN_ARGOCD_COMPARE_OPTIONS}: ServerSideDiff=false` — "
                f"Argo SSA will reject immutable dataSourceRef changes."
            )

    # Namespace privileged-movers label check (required for ClusterES to materialize the Secret).
    # Skip for unknown — classification isn't settled yet, so it's spurious until the operator/user
    # decides whether the PVC should be backed up at all.
    ns_doc = idx.namespaces.get(ns)
    if ns_doc is not None:
        ns_labels = labels(ns_doc)
        if ns_labels.get(NAMESPACE_PRIVILEGED_MOVERS_LABEL, "").lower() not in ("true", "1", "yes"):
            if classification in ("inline-argo", "helm-rendered", "orphan-cluster"):
                blockers.append(
                    f"namespace '{ns}' missing label "
                    f"`{NAMESPACE_PRIVILEGED_MOVERS_LABEL}: \"true\"` — "
                    f"ClusterES will not materialize the {SHARED_REPO_SECRET} Secret here."
                )
    else:
        notes.append(f"no Namespace manifest rendered for {ns} (may be created by another path)")

    # Legacy backup label.
    if legacy_backup_tier:
        notes.append(
            f"legacy label `backup: {legacy_backup_tier}` still present — "
            f"safe to strip (operator dead) but harmless."
        )

    # pvc-plumber.io/enabled is not yet expected anywhere. Note if it's already set.
    if pvc_plumber_enabled:
        notes.append("pvc-plumber.io/enabled already set — early-adopter PVC.")

    # Migration recommendation.
    rec = build_recommendation(
        classification,
        blockers,
        exempt,
        has_inline_wiring,
        pvc_spec.get("storageClassName", "") or "",
    )

    return PVCRow(
        namespace=ns,
        app_path=", ".join(sorted(render_paths_for_pvc)),
        pvc_name=nm,
        workload_claim_refs=workload_refs,
        storage_class=pvc_spec.get("storageClassName", "") or "",
        requested_size=pvc_request_size(pvc),
        access_modes=pvc_access_modes(pvc),
        current_data_source_ref=ds_str,
        expected_rd=expected_rd,
        current_rd=name(rd_doc) if rd_doc else "",
        expected_rs=expected_rs,
        current_rs=name(rs_doc) if rs_doc else "",
        repo_secret_ref=repo_secret,
        backup_identity=backup_identity,
        mover_uid=mover_uid,
        mover_gid=mover_gid,
        mover_fsgroup=mover_fsgroup,
        schedule=schedule,
        tier=tier,
        restore_policy=restore_policy,
        pvc_plumber_enabled=pvc_plumber_enabled,
        pvc_plumber_tier=pvc_plumber_tier,
        pvc_plumber_mode=pvc_plumber_mode,
        classification=classification,
        migration_recommendation=rec,
        blockers=blockers,
        notes=notes,
    )


def _snapshot_capable_storage_class(sc: str) -> bool:
    """True if the storage class is known to support CSI VolumeSnapshots, which
    VolSync requires. Conservative — only 'longhorn' is explicitly opted in."""
    return sc.lower() == "longhorn"


def build_recommendation(
    classification: str,
    blockers: list[str],
    exempt: bool,
    has_inline: bool,
    storage_class: str,
) -> str:
    if classification == "cnpg-excluded":
        return "No action — CNPG/Barman path; explicitly out of pvc-plumber scope."
    if classification == "backup-exempt":
        if blockers:
            return "Block: fix backup-exempt reason annotation before any phase touches this PVC."
        return "No action — operator will skip; keep `backup-exempt: \"true\"` label."
    if classification == "inline-argo":
        if blockers:
            return "Phase 4 parity: resolve blockers before Phase 7 cutover."
        return ("Phase 7 cutover candidate: add `pvc-plumber.io/enabled: \"true\"` "
                "+ tier; remove inline RS/RD doc in same commit; verify audit "
                "log says 'would recreate identical resource' before merge.")
    if classification == "helm-rendered":
        if blockers:
            return "Phase 4 parity: resolve blockers before Phase 7 special-case cutover."
        return ("Phase 7 special-case: keep Kustomize `patches:` for "
                "ServerSideDiff/dataSourceRef; remove RS/RD from chart "
                "`extraDeploy:` or values once operator adopts.")
    if classification == "orphan-cluster":
        return ("Phase 1 attention: confirm orphan via cluster query; either "
                "add inline RS/RD to Git in the matching app dir now, or wait "
                "for Phase 6 operator adoption (which will relabel the cluster "
                "resource with `app.kubernetes.io/managed-by: pvc-plumber`).")
    # classification == "unknown" — branch on storage class for actionable advice.
    if not _snapshot_capable_storage_class(storage_class):
        sc_label = storage_class or "(static PV / no storage class)"
        return (f"Storage class `{sc_label}` does not support CSI VolumeSnapshots "
                f"and cannot be VolSync-backed. **Recommend marking "
                f"`backup-exempt: \"true\"` with annotation "
                f"`{ANN_BACKUP_EXEMPT_REASON_FQ}: \"<reason>\"`.** Decide and "
                f"record before Phase 7.")
    return ("Storage class `longhorn` supports snapshots. **Decision required**: "
            "either wire up inline RS/RD per `.claude/commands/add-backup.md` "
            "(then it'll classify as inline-argo), or mark `backup-exempt: "
            "\"true\"` with FQ reason annotation. Don't leave unresolved past Phase 7.")


# ---------------------------------------------------------------------------
# Report writer.
# ---------------------------------------------------------------------------


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def write_markdown(
    out_path: Path,
    rows: list[PVCRow],
    render_failures: dict[str, str],
    cluster_state: ClusterState | None,
    cluster_orphans_extra: list[str],
    timestamp: str,
    repo_head: str,
) -> None:
    by_class: dict[str, list[PVCRow]] = defaultdict(list)
    for row in rows:
        by_class[row.classification].append(row)

    total = len(rows)
    counts = {c: len(by_class.get(c, [])) for c in CLASSIFICATIONS}
    protected = counts["inline-argo"] + counts["helm-rendered"] + counts["orphan-cluster"]

    total_blockers = sum(len(r.blockers) for r in rows)
    pvc_with_blockers = sum(1 for r in rows if r.blockers)

    lines: list[str] = []
    lines += [
        "# pvc-plumber v4 — Phase 1 Inventory",
        "",
        f"Generated by `hack/pvc-plumber-inventory.py` at {timestamp}.",
        f"Repo HEAD: `{repo_head}`.",
        f"Cluster cross-reference: {'enabled' if cluster_state else 'disabled (run with --with-cluster)'}.",
        "",
        "> This is a **read-only** inventory. The generator script invokes only "
        "`kustomize build --enable-helm`, `kubectl get ... -o json`, and "
        "`git rev-parse` — all read paths. No app manifests, operator code, "
        "kustomizations, Argo Applications, ClusterES, MAP, or cluster state "
        "have been modified. Phase 1 of `docs/pvc-plumber-v4-prd.md`. "
        "Re-generate with `python3 hack/pvc-plumber-inventory.py "
        "[--with-cluster]` — `--with-cluster` is opt-in and adds no write paths.",
        "",
        "## Two sources of truth",
        "",
        "Every row in this inventory is built from one or both of:",
        "",
        "- **Git-rendered truth**: the output of `kustomize build --enable-helm` "
            "on every kustomization directory under `my-apps/` and "
            "`infrastructure/` (excluding CNPG, container-registry, and storage "
            "operators). This is what Argo CD would apply to the cluster. PVCs, "
            "ReplicationSources, and ReplicationDestinations appearing in this "
            "render are the Git source of truth.",
        "- **Live cluster truth**: the output of `kubectl get "
            "replicationsource,replicationdestination -A -o json` against the "
            "current kubectl context. Only consulted with `--with-cluster`.",
        "",
        "Classifications combine both sources:",
        "",
        "| Classification | Git truth | Live cluster truth |",
        "| --- | --- | --- |",
        "| `inline-argo` | PVC + RS + RD all rendered from Git | usually mirrored; legacy `-backup` names surfaced as notes |",
        "| `helm-rendered` | PVC from chart + Kustomize patches inject dataSourceRef + RS/RD from chart `extraDeploy:` | same as `inline-argo` |",
        "| `orphan-cluster` | PVC exists in Git, no inline RS/RD | RS/RD present in cluster only (e.g. legacy `<pvc>-backup`) |",
        "| `backup-exempt` | PVC carries `backup-exempt: \"true\"` label | not consulted |",
        "| `cnpg-excluded` | PVC in `cloudnative-pg` namespace or labeled `cnpg.io/cluster` | not consulted (Barman path) |",
        "| `unknown` | PVC in Git, no inline RS/RD, no cluster RS/RD | (negative result from cluster) |",
        "",
        "The **Cluster-only orphan RS/RD** section (further down) lists cluster "
        "resources that have **no matching PVC in Git** — these cannot be "
        "classified as PVC rows because the PVC itself isn't there.",
        "",
        "## Reconciling against the prior handoff doc",
        "",
        "> **The figure of \"27 orphan apps still unmigrated\" cited in "
        "`docs/research/pvc-backup-simplification/CLEANUP-IN-PROGRESS.md` "
        "(2026-05-21) is stale.** That document captured the cluster state at "
        "the time the pvc-plumber operator was decommissioned, before the "
        "inline-RS/RD bulk migration ran to completion. As of this inventory "
        "(repo HEAD above), the cluster cross-reference finds **0 PVCs whose "
        "Git-rendered PVC lacks a matching live RS/RD**. The only cluster-only "
        "leftovers are the 4 copyparty objects listed below, whose Git PVCs "
        "were themselves removed (so they are dangling RS/RD without any "
        "corresponding PVC, Git or live).",
        "",
        "## Summary",
        "",
        f"- **Total PVCs in inventory**: {total}",
        f"- **Protected PVC count** (inline-argo + helm-rendered + orphan-cluster): {protected}",
        f"- **inline-argo**: {counts['inline-argo']} (current pattern — Git owns PVC + RS + RD)",
        f"- **helm-rendered**: {counts['helm-rendered']} (chart-owned PVC + Kustomize patches inject dataSourceRef)",
        f"- **orphan-cluster**: {counts['orphan-cluster']} (RS/RD exists in cluster only; needs cleanup or adoption in Phase 6)",
        f"- **backup-exempt**: {counts['backup-exempt']}",
        f"- **cnpg-excluded**: {counts['cnpg-excluded']}",
        f"- **unknown**: {counts['unknown']} (needs human review)",
        f"- **PVCs with blockers**: {pvc_with_blockers} (across {total_blockers} blocker entries)",
        "",
    ]

    if render_failures:
        lines += [
            "## Render failures",
            "",
            "These kustomization directories failed to render. They are excluded "
            "from the inventory below. **Fix before Phase 4 parity check.**",
            "",
        ]
        for path, err in sorted(render_failures.items()):
            first_line = err.splitlines()[0] if err else "failed"
            lines.append(f"- `{path}` — {md_escape(first_line)}")
        lines.append("")

    # Top blockers before pvc-plumber audit mode.
    lines += ["## Top blockers before pvc-plumber audit mode", ""]
    top_blockers = collect_top_blockers(rows, cluster_state, cluster_orphans_extra)
    if top_blockers:
        for blocker in top_blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- (none found — proceed to Phase 2)")
    lines.append("")

    if cluster_orphans_extra:
        lines += [
            "## Cluster-only orphan RS/RD (no corresponding PVC in Git)",
            "",
            "These resources exist in the cluster but have no matching PVC in "
            "the rendered Git tree. They may be leftover from deleted apps, "
            "renamed PVCs, or namespaces. **Investigate before Phase 6 "
            "adoption.**",
            "",
        ]
        for orphan in cluster_orphans_extra:
            lines.append(f"- {orphan}")
        lines.append("")

    # Per-classification sections — compact tables.
    for cls in CLASSIFICATIONS:
        cls_rows = by_class.get(cls, [])
        if not cls_rows:
            continue
        lines += [
            f"## Classification: `{cls}` ({len(cls_rows)})",
            "",
            "| namespace | pvc | size | storageClass | restore-policy | tier | RS | RD | blockers |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in sorted(cls_rows, key=lambda r: (r.namespace, r.pvc_name)):
            lines.append(
                "| "
                + " | ".join(
                    md_escape(v) for v in [
                        row.namespace,
                        row.pvc_name,
                        row.requested_size,
                        row.storage_class,
                        row.restore_policy,
                        row.tier or row.schedule,
                        ("✓ " + row.current_rs) if row.current_rs else "—",
                        ("✓ " + row.current_rd) if row.current_rd else "—",
                        str(len(row.blockers)) if row.blockers else "",
                    ]
                )
                + " |"
            )
        lines.append("")

    # Per-PVC detail blocks for everything that has blockers, plus all
    # orphan-cluster and unknown rows.
    detail_rows = [
        r for r in rows
        if r.blockers
        or r.classification in ("orphan-cluster", "unknown")
        or r.notes
    ]
    if detail_rows:
        lines += [
            "## Per-PVC detail (rows with blockers, notes, orphans, or unknowns)",
            "",
        ]
        for row in sorted(detail_rows, key=lambda r: (r.classification, r.namespace, r.pvc_name)):
            lines += [
                f"### `{row.namespace}/{row.pvc_name}` — {row.classification}",
                "",
                f"- **Path**: `{row.app_path}`",
                f"- **Workload refs**: {', '.join(row.workload_claim_refs) or '(none rendered)'}",
                f"- **Size / SC / accessModes**: {row.requested_size} / {row.storage_class} / {','.join(row.access_modes)}",
                f"- **dataSourceRef (current)**: `{row.current_data_source_ref or '—'}`",
                f"- **RS (expected / current)**: `{row.expected_rs}` / `{row.current_rs or '—'}`",
                f"- **RD (expected / current)**: `{row.expected_rd}` / `{row.current_rd or '—'}`",
                f"- **Backup identity**: `{row.backup_identity}`",
                f"- **Mover UID/GID/fsGroup**: `{row.mover_uid}/{row.mover_gid}/{row.mover_fsgroup}`",
                f"- **Schedule / tier**: `{row.schedule}` / `{row.tier}`",
                f"- **Restore-policy**: `{row.restore_policy or '(unset)'}`",
                f"- **pvc-plumber.io/enabled**: {'yes' if row.pvc_plumber_enabled else 'no'}, tier=`{row.pvc_plumber_tier or '—'}`, mode=`{row.pvc_plumber_mode or '—'}`",
                f"- **Recommendation**: {row.migration_recommendation}",
            ]
            if row.blockers:
                lines.append("- **Blockers**:")
                for b in row.blockers:
                    lines.append(f"  - {b}")
            if row.notes:
                lines.append("- **Notes**:")
                for n in row.notes:
                    lines.append(f"  - {n}")
            lines.append("")

    out_path.write_text("\n".join(lines))


def collect_top_blockers(
    rows: list[PVCRow],
    cluster_state: ClusterState | None,
    cluster_orphans_extra: list[str],
) -> list[str]:
    top: list[str] = []
    # Aggregated blocker counts.
    pvcs_with_blockers = [r for r in rows if r.blockers]
    if pvcs_with_blockers:
        top.append(
            f"**{len(pvcs_with_blockers)} PVCs have wiring blockers** that must "
            "be resolved before Phase 4 parity verification. See per-PVC detail "
            "blocks below."
        )
    # Orphan cluster resources.
    orphan_count = sum(1 for r in rows if r.classification == "orphan-cluster")
    if orphan_count:
        top.append(
            f"**{orphan_count} PVCs classified `orphan-cluster`** — their RS/RD "
            "live in the cluster only, not in Git. A PVC recreate is silent "
            "data loss until Phase 6 adoption or manual inline RS/RD addition."
        )
    if cluster_orphans_extra:
        top.append(
            f"**{len(cluster_orphans_extra)} cluster RS/RD have no matching "
            "PVC in Git.** These are likely deleted-app leftovers; clean up "
            "before Phase 6."
        )
    # Unknown.
    unknown_count = sum(1 for r in rows if r.classification == "unknown")
    if unknown_count:
        top.append(
            f"**{unknown_count} PVCs classified `unknown`** — needs human "
            "review; classification logic was indeterminate."
        )
    # CLAUDE.md drift in the inventory itself (handled in Phase 0, but defensive note).
    if cluster_state is not None and cluster_state.error:
        top.append(f"**Cluster query error**: {cluster_state.error}")
    return top


# ---------------------------------------------------------------------------
# CSV companion writer.
# ---------------------------------------------------------------------------


def write_csv(out_path: Path, rows: list[PVCRow]) -> None:
    if not rows:
        out_path.write_text("")
        return
    header = list(rows[0].to_dict().keys())
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r.classification, r.namespace, r.pvc_name)):
            writer.writerow(row.to_dict())


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def repo_head_commit(root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="pvc-plumber v4 Phase 1 inventory (read-only).",
    )
    parser.add_argument("--repo-root", default=".", help="repository root (default: cwd)")
    parser.add_argument(
        "--output",
        default="docs/pvc-plumber-v4-inventory.md",
        help="markdown report output path",
    )
    parser.add_argument(
        "--csv",
        default="docs/pvc-plumber-v4-inventory.csv",
        help="CSV report output path (full column set)",
    )
    parser.add_argument(
        "--with-cluster",
        action="store_true",
        help=(
            "Cross-reference against live cluster via read-only kubectl "
            "get rs,rd -A -o json. NEVER mutates state."
        ),
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()

    # Render.
    print(f"[1/4] Discovering kustomization directories under {root}...", file=sys.stderr)
    dirs = kustomization_dirs(root, EXCLUDE_DIRS)
    print(f"      → {len(dirs)} directories to render", file=sys.stderr)

    print("[2/4] Rendering kustomizations with --enable-helm (this may take a minute)...", file=sys.stderr)
    helm_dirs: set[str] = set()
    all_docs: list[dict[str, Any]] = []
    render_failures: dict[str, str] = {}
    for d in dirs:
        rel = str(d.relative_to(root))
        if kustomization_uses_helm(d):
            helm_dirs.add(rel)
        docs, err = render_path(root, d)
        if err:
            render_failures[rel] = err
        else:
            all_docs.extend(docs)
    print(f"      → {len(all_docs)} docs rendered, {len(render_failures)} render failures", file=sys.stderr)

    # Index.
    print("[3/4] Building indexes and classifying PVCs...", file=sys.stderr)
    idx = build_index(all_docs, helm_dirs)
    print(f"      → {len(idx.pvcs)} PVCs, {len(idx.rss)} RS, {len(idx.rds)} RD in Git", file=sys.stderr)

    # Cluster cross-reference (optional).
    cluster_state: ClusterState | None = None
    cluster_orphans_extra: list[str] = []
    if args.with_cluster:
        print("[3.5/4] Querying cluster for orphan RS/RD (read-only)...", file=sys.stderr)
        cluster_state = query_cluster()
        if cluster_state.error:
            print(f"        WARN: {cluster_state.error}", file=sys.stderr)
        else:
            # Extra orphans: cluster RS/RD that have no corresponding PVC in Git.
            for (ns, rs_name) in sorted(cluster_state.rss):
                if ns in SYSTEM_NAMESPACES:
                    continue
                # The RS's sourcePVC is what matters — but we also want to flag
                # RS that aren't pointed at any Git-rendered PVC.
                source_pvc = next(
                    (s for (n, s), name_ in cluster_state.rss_by_pvc.items()
                     if n == ns and name_ == rs_name),
                    None,
                )
                if source_pvc and (ns, source_pvc) not in idx.pvcs:
                    mgr = cluster_state.rss_managed_by.get((ns, rs_name), "")
                    cluster_orphans_extra.append(
                        f"`{ns}/{rs_name}` (RS, managed-by=`{mgr}`) — sourcePVC `{source_pvc}` has no PVC in Git"
                    )
            for (ns, rd_name) in sorted(cluster_state.rds):
                if ns in SYSTEM_NAMESPACES:
                    continue
                # Heuristic: an RD whose stripped name (-dst / -backup) doesn't
                # match any rendered PVC is suspicious.
                candidate_pvc_names = [
                    rd_name,
                    rd_name.removesuffix("-dst"),
                    rd_name.removesuffix("-backup"),
                ]
                if not any((ns, c) in idx.pvcs for c in candidate_pvc_names):
                    mgr = cluster_state.rds_managed_by.get((ns, rd_name), "")
                    cluster_orphans_extra.append(
                        f"`{ns}/{rd_name}` (RD, managed-by=`{mgr}`) — no PVC `{candidate_pvc_names[0]}` / "
                        f"`{candidate_pvc_names[1]}` / `{candidate_pvc_names[2]}` in Git"
                    )

    # Build rows.
    rows: list[PVCRow] = []
    for key, pvc in sorted(idx.pvcs.items()):
        ns, _ = key
        if ns in SYSTEM_NAMESPACES:
            continue
        render_paths_for_pvc = idx.render_paths.get(("PersistentVolumeClaim", key[0], key[1]), set())
        rows.append(build_row(pvc, idx, cluster_state, render_paths_for_pvc))

    # Write outputs.
    print("[4/4] Writing report...", file=sys.stderr)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    head = repo_head_commit(root)
    md_path = root / args.output
    csv_path = root / args.csv
    write_markdown(md_path, rows, render_failures, cluster_state, cluster_orphans_extra, timestamp, head)
    write_csv(csv_path, rows)
    print(f"      → {md_path.relative_to(root)} ({len(rows)} PVCs)", file=sys.stderr)
    print(f"      → {csv_path.relative_to(root)}", file=sys.stderr)

    # stdout summary for piping.
    by_class: dict[str, int] = defaultdict(int)
    for r in rows:
        by_class[r.classification] += 1
    summary = {
        "timestamp": timestamp,
        "repo_head": head,
        "with_cluster": bool(cluster_state),
        "total_pvcs": len(rows),
        "by_classification": dict(by_class),
        "render_failures": len(render_failures),
        "pvcs_with_blockers": sum(1 for r in rows if r.blockers),
        "cluster_orphans_extra": len(cluster_orphans_extra),
        "report": str(md_path.relative_to(root)),
        "csv": str(csv_path.relative_to(root)),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    # Exit 0 — read-only tool, never fails. Caller decides what to do with the report.
    return 0


if __name__ == "__main__":
    sys.exit(main())
