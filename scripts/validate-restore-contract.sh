#!/usr/bin/env bash
# Enforce the pvc-plumber v4 restore contract on RENDERED manifests.
#
# Why this exists:
#   A PVC can opt in to operator-managed backups (labels
#   `pvc-plumber.io/enabled: "true"` + `pvc-plumber.io/manage-volsync:
#   "true"`) and back up successfully forever — yet still recreate EMPTY
#   during DR if its Git manifest lacks the static restore reference:
#
#     spec.dataSourceRef:
#       apiGroup: volsync.backube
#       kind: ReplicationDestination
#       name: <pvc-name>-dst
#
#   Backup is not restore. The 2026-06-02 full-nuke acceptance proved the
#   contract end-to-end for every PVC that had it; nothing prevented the
#   NEXT PVC from shipping without it. This script closes that gap.
#
#   It validates RENDERED output (kustomize build --enable-helm), not raw
#   YAML, because Helm-rendered PVCs carry the same contract — e.g.
#   gitea/gitea-shared-storage, which is invisible to a static grep of
#   the repo (the 2026-06-09 review's static count missed it).
#
# Contract checked, per rendered PVC with BOTH fuse labels set:
#   1. backup-exempt: "true"        -> excluded from the requirement.
#   2. tier "disabled"              -> must NOT carry a dataSourceRef
#                                      (the operator deletes the RD, so a
#                                      ref would wedge the PVC Pending on
#                                      rebuild).
#   3. otherwise                    -> dataSourceRef must be exactly
#                                      {volsync.backube, ReplicationDestination,
#                                      <pvc>-dst}, and the PVC's namespace
#                                      must carry
#                                      pvc-plumber.io/managed-namespace: "true".
#
#   CNPG data PVCs are operator-created at runtime (never rendered from
#   Git) and PostHog/Redis are backup-exempt without fuse labels, so
#   none of them can trip this check.
#
# Usage:
#   scripts/validate-restore-contract.sh [rendered-manifests.yaml]
#
#   With an argument, validates the given pre-rendered multi-doc YAML
#   (CI passes the render-and-schema job's /tmp/all-manifests.yaml so the
#   expensive render happens once). Without, renders every kustomization
#   under infrastructure/ monitoring/ my-apps/ itself.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RENDERED="${1:-}"
if [ -z "$RENDERED" ]; then
  RENDERED="$(mktemp /tmp/restore-contract-render.XXXXXX.yaml)"
  trap 'rm -f "$RENDERED"' EXIT
  mapfile -t dirs < <(find infrastructure monitoring my-apps -type f -name kustomization.yaml -exec dirname {} \; | sort -u)
  if [ "${#dirs[@]}" -eq 0 ]; then
    echo "No kustomization directories found." >&2
    exit 1
  fi
  for dir in "${dirs[@]}"; do
    echo "Rendering ${dir}" >&2
    kustomize build "${dir}" --enable-helm >> "$RENDERED"
    echo "---" >> "$RENDERED"
  done
fi

python3 - "$RENDERED" <<'PYEOF'
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("ERROR: python3 PyYAML is required (pip install pyyaml)")

try:
    Loader = yaml.CSafeLoader
except AttributeError:
    Loader = yaml.SafeLoader

ENABLED = "pvc-plumber.io/enabled"
MANAGE = "pvc-plumber.io/manage-volsync"
TIER = "pvc-plumber.io/tier"
EXEMPT = "backup-exempt"
NS_GATE = "pvc-plumber.io/managed-namespace"

namespaces = {}  # name -> managed (bool)
pvcs = {}        # (ns, name) -> doc, deduped (parent+child kustomizations render twice)

# Some rendered docs (e.g. Grafana dashboard ConfigMaps) embed exotic YAML
# tags that SafeLoader rejects. Parse per-document so one bad doc can't
# abort the scan — but a doc that fails to parse may only be skipped if
# it is provably not a PVC or Namespace manifest.
KIND_RE = re.compile(r"^kind:\s*(PersistentVolumeClaim|Namespace)\s*$", re.M)

with open(sys.argv[1]) as f:
    raw = f.read()

unparseable = []
for chunk in re.split(r"^---\s*$", raw, flags=re.M):
    if not chunk.strip():
        continue
    try:
        doc = yaml.load(chunk, Loader=Loader)
    except yaml.YAMLError:
        if KIND_RE.search(chunk):
            unparseable.append(chunk.strip().splitlines()[0])
        continue
    if not isinstance(doc, dict):
        continue
    kind = doc.get("kind")
    meta = doc.get("metadata") or {}
    labels = meta.get("labels") or {}
    if kind == "Namespace":
        managed = str(labels.get(NS_GATE, "")).lower() == "true"
        # A namespace rendered by several apps: managed if ANY render says so.
        namespaces[meta.get("name")] = namespaces.get(meta.get("name"), False) or managed
    elif kind == "PersistentVolumeClaim":
        pvcs[(meta.get("namespace"), meta.get("name"))] = doc

if unparseable:
    sys.exit("ERROR: %d PVC/Namespace document(s) failed to parse; cannot validate: %s"
             % (len(unparseable), unparseable[:3]))

errors = []
checked = 0

for (ns, name), doc in sorted(pvcs.items()):
    labels = (doc.get("metadata") or {}).get("labels") or {}
    if str(labels.get(ENABLED, "")).lower() != "true":
        continue
    if str(labels.get(MANAGE, "")).lower() != "true":
        continue
    if str(labels.get(EXEMPT, "")).lower() == "true":
        continue  # exempt PVCs are excluded from the restore requirement
    checked += 1

    spec = doc.get("spec") or {}
    ref = spec.get("dataSourceRef") or {}
    tier = str(labels.get(TIER, "")).strip('"').lower()

    if tier == "disabled":
        if ref:
            errors.append(
                f"PVC {ns}/{name} has tier=disabled (operator deletes the RD) but still "
                f"carries a dataSourceRef; it would recreate Pending-forever during DR.")
        continue

    expected = f"{name}-dst"
    if not ref:
        errors.append(
            f"PVC {ns}/{name} is pvc-plumber-managed but missing dataSourceRef to "
            f"{expected}; it would recreate empty during DR.")
        continue
    if (ref.get("apiGroup") != "volsync.backube"
            or ref.get("kind") != "ReplicationDestination"
            or ref.get("name") != expected):
        errors.append(
            f"PVC {ns}/{name} dataSourceRef is {ref.get('apiGroup')}/{ref.get('kind')}/"
            f"{ref.get('name')}, expected volsync.backube/ReplicationDestination/{expected}; "
            f"a mismatched ref restores nothing and the PVC would recreate empty during DR.")

    if ns is None:
        errors.append(
            f"PVC <no-namespace>/{name} is pvc-plumber-managed but renders without "
            f"metadata.namespace; the namespace gate cannot be verified.")
    elif ns not in namespaces:
        errors.append(
            f"PVC {ns}/{name} is pvc-plumber-managed but no rendered Namespace manifest "
            f"for '{ns}' was found; cannot verify {NS_GATE}.")
    elif not namespaces[ns]:
        errors.append(
            f"PVC {ns}/{name} is pvc-plumber-managed but namespace '{ns}' lacks "
            f"{NS_GATE}: \"true\"; the operator will refuse to write RS/RD "
            f"(skipped-namespace-not-managed) and the PVC has no backup.")

if errors:
    for e in errors:
        print(f"ERROR: {e}")
    print()
    print("FAIL: pvc-plumber restore contract violation "
          "(see docs/disaster-recovery.md and .claude/commands/add-backup.md).")
    sys.exit(1)

print(f"OK: {checked} managed PVC(s) satisfy the restore contract "
      f"(dataSourceRef -> <pvc>-dst + managed namespace); "
      f"{len(namespaces)} namespaces seen.")
PYEOF
