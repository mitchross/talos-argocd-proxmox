#!/usr/bin/env python3
"""Validate kopiur backup coverage against a RENDERED manifest stream.

Replaces the retired pvc-plumber `validate-restore-contract.sh` and folds in the
now-dead `backup-exempt-contract` job. kopiur has no `/audit` ledger, so this is
the CI guard that catches the silent gaps that ledger used to surface.

Runs on the rendered kustomize stream (so Helm-rendered PVCs — gitea, tubesync —
are covered, which a static grep of *.yaml cannot do).

    python3 scripts/validate-kopiur-coverage.py /tmp/all-manifests.yaml

HARD FAILS (exit 1):
  [dsr]     A backed-up PVC (target of a kopiur SnapshotPolicy) whose
            spec.dataSourceRef does NOT point at a kopiur Restore → it recreates
            EMPTY in DR. The single most dangerous silent gap.
  [nslabel] A namespace containing a SnapshotPolicy that lacks the
            `kopiur.home-operations.com/repo: cluster-kopia` label → the
            ClusterExternalSecret won't fan the repo creds in; the mover can't auth.

WARNINGS (printed, exit 0):
  [mover]   A SnapshotPolicy/Restore with no spec.mover security context (neither
            securityContext nor inheritSecurityContextFrom) → likely PermissionDenied
            (the #1 kopiur gotcha — see docs/domains/storage/kopiur-mover-permissions.md).
  [gap]     A longhorn PVC that is neither backed up nor backup-exempt → review.
  [exempt]  A backup-exempt PVC missing the fully-qualified reason annotation
            (kept for grep-ability now that pvc-plumber no longer enforces it).
"""
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("pyyaml required: pip3 install pyyaml\n")
    sys.exit(2)

KOPIUR_GROUP = "kopiur.home-operations.com"
REPO_LABEL = "kopiur.home-operations.com/repo"
REPO_LABEL_VAL = "cluster-kopia"
EXEMPT_LABEL = "backup-exempt"
EXEMPT_REASON = "storage.vanillax.dev/backup-exempt-reason"
SYSTEM_NS = {
    "kube-system", "argocd", "longhorn-system", "kopiur-system", "cert-manager",
    "external-secrets", "kube-node-lease", "kube-public", "monitoring", "gateway",
    "1passwordconnect", "volsync-system",
}


def meta(d, key):
    return (d.get("metadata") or {}).get(key)


def labels_of(d):
    return (d.get("metadata") or {}).get("labels") or {}


def anns_of(d):
    return (d.get("metadata") or {}).get("annotations") or {}


def has_mover_sc(d):
    mover = (d.get("spec") or {}).get("mover") or {}
    return bool(mover.get("securityContext") or mover.get("inheritSecurityContextFrom"))


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: validate-kopiur-coverage.py <rendered-manifests.yaml>\n")
        return 2

    # kube-prometheus-stack CRDs contain a bare `=` enum value (AlertManager
    # matchType), which PyYAML maps to the special value-tag and otherwise fails
    # to construct. Treat it as a literal scalar so the rendered stream parses.
    yaml.SafeLoader.add_constructor(
        "tag:yaml.org,2002:value", lambda loader, node: loader.construct_scalar(node)
    )

    with open(sys.argv[1]) as fh:
        docs = [d for d in yaml.safe_load_all(fh) if isinstance(d, dict) and d.get("kind")]

    pvcs, namespaces, policies, restores = {}, {}, [], []
    for d in docs:
        kind = d.get("kind")
        group = (d.get("apiVersion") or "").split("/")[0]
        if kind == "PersistentVolumeClaim":
            pvcs[(meta(d, "namespace"), meta(d, "name"))] = d
        elif kind == "Namespace":
            namespaces[meta(d, "name")] = d
        elif group == KOPIUR_GROUP and kind == "SnapshotPolicy":
            policies.append(d)
        elif group == KOPIUR_GROUP and kind == "Restore":
            restores.append(d)

    fails, warns = [], []
    backed_pvcs, backed_namespaces = set(), set()

    for p in policies:
        pns, pname = meta(p, "namespace"), meta(p, "name")
        backed_namespaces.add(pns)
        if not has_mover_sc(p):
            warns.append(f"[mover]   SnapshotPolicy {pns}/{pname}: no spec.mover security context (set the data-owner uid:gid)")
        for src in ((p.get("spec") or {}).get("sources") or []):
            pvcname = (src.get("pvc") or {}).get("name")
            if not pvcname:
                continue
            backed_pvcs.add((pns, pvcname))
            pvc = pvcs.get((pns, pvcname))
            if pvc is None:
                fails.append(f"[dsr]     SnapshotPolicy {pns}/{pname} backs up PVC '{pvcname}' but no such PVC was rendered")
                continue
            dsr = (pvc.get("spec") or {}).get("dataSourceRef") or {}
            if dsr.get("apiGroup") != KOPIUR_GROUP or dsr.get("kind") != "Restore":
                fails.append(f"[dsr]     PVC {pns}/{pvcname} is backed up but dataSourceRef is not a kopiur Restore → recreates EMPTY in DR (got: {dsr or 'none'})")

    for r in restores:
        if not has_mover_sc(r):
            warns.append(f"[mover]   Restore {meta(r, 'namespace')}/{meta(r, 'name')}: no spec.mover security context")

    for ns in sorted(backed_namespaces):
        nd = namespaces.get(ns)
        if nd is None:
            warns.append(f"[nslabel] namespace '{ns}' has kopiur stubs but no Namespace object rendered (can't verify repo label)")
        elif labels_of(nd).get(REPO_LABEL) != REPO_LABEL_VAL:
            fails.append(f"[nslabel] namespace '{ns}' is backed up but missing label {REPO_LABEL}={REPO_LABEL_VAL} → repo creds won't fan in")

    for (pns, pname), pvc in sorted(pvcs.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        if pns in SYSTEM_NS:
            continue
        if (pvc.get("spec") or {}).get("storageClassName") != "longhorn":
            continue
        lbls = labels_of(pvc)
        if any(k.startswith("cnpg.io/") for k in lbls):  # CNPG = Barman, not kopiur
            continue
        if (pns, pname) in backed_pvcs:
            continue
        if lbls.get(EXEMPT_LABEL) == "true":
            if not anns_of(pvc).get(EXEMPT_REASON):
                warns.append(f"[exempt]  PVC {pns}/{pname} is backup-exempt but missing {EXEMPT_REASON} annotation")
            continue
        warns.append(f"[gap]     PVC {pns}/{pname} (longhorn) is neither backed up nor backup-exempt → review")

    print("== kopiur backup coverage ==")
    print(f"  policies={len(policies)} restores={len(restores)} pvcs={len(pvcs)} backed-namespaces={len(backed_namespaces)}")
    for w in warns:
        print(f"  WARN {w}")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\n{len(fails)} hard failure(s): a backup would silently fail or a PVC would recreate empty in DR.")
        return 1
    print(f"\nOK — coverage intact ({len(warns)} warning(s), 0 failures).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
