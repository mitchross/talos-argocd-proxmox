#!/usr/bin/env python3
"""Print a short status for a node drain or reboot: what blocks it and how long the copies take."""
import argparse
import json
import os
import subprocess
import urllib.parse
import urllib.request

PROM = os.environ.get("PROM_URL", "http://kube-prometheus-stack-prometheus.prometheus-stack.svc:9090")
LH = "longhorn-system"
STAGES = {0: "UNKNOWN", 1: "BOOTING", 2: "INSTALLING", 3: "CONFIGURING", 4: "RUNNING", 5: "DESTROYING",
          6: "UPGRADING", 7: "REBOOTING", 8: "SHUTTING_DOWN", 9: "BEFORE_DESTROY", 10: "POWERING_ON",
          11: "POWERED_OFF"}
APPLY = {0: "UNKNOWN", 1: "PENDING", 2: "APPLIED", 3: "FAILED"}
GiB = 2 ** 30


def kube(*args):
    out = subprocess.run(["kubectl", *args, "-o", "json"], capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout)["items"]


def prom(expr) -> list[dict]:
    url = PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    try:
        return json.load(urllib.request.urlopen(url, timeout=30))["data"]["result"]
    except Exception as e:  # noqa: BLE001
        return [{"error": str(e)}]


def omni_machines():
    env = os.environ.copy()
    try:
        out = subprocess.run(["omnictl", "get", "clustermachinestatus", "-o", "json"], capture_output=True,
                             text=True, timeout=60, env=env)
    except FileNotFoundError:
        return None, "omnictl not on PATH (source /opt/data/tools/talos-env.sh)"
    if out.returncode:
        return None, out.stderr.strip()[:200]
    dec, text, i, items = json.JSONDecoder(), out.stdout, 0, []
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        obj, i = dec.raw_decode(text, i)
        items.append(obj)
    return items, None


def pvc_name(vol):
    ks = vol.get("status", {}).get("kubernetesStatus", {})
    return f'{ks.get("namespace") or "?"}/{ks.get("pvcName") or vol["metadata"]["name"]}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", help="node you plan to drain or reboot; lists the copies it would cause")
    args = ap.parse_args()
    lines = []

    nodes = kube("get", "nodes")
    cordoned = [n["metadata"]["name"] for n in nodes if n["spec"].get("unschedulable")]
    vols = {v["metadata"]["name"]: v for v in kube("get", "volumes.longhorn.io", "-n", LH)}
    reps = [r for r in kube("get", "replicas.longhorn.io", "-n", LH) if not r["spec"].get("failedAt")]
    lhnodes = kube("get", "nodes.longhorn.io", "-n", LH)
    scs = kube("get", "storageclass")

    placed = {}
    for r in reps:
        if r["spec"].get("nodeID"):
            placed.setdefault(r["spec"]["volumeName"], []).append(r)

    lines.append("**Drain status**")
    lines.append(f"- Cordoned nodes: {', '.join(cordoned) or 'none'}")

    evict = [r for r in reps if r["spec"].get("evictionRequested")]
    by_node = {}
    for r in evict:
        by_node.setdefault(r["spec"]["nodeID"], []).append(pvc_name(vols.get(r["spec"]["volumeName"], {"metadata": {"name": r["spec"]["volumeName"]}})))
    if by_node:
        for n, v in sorted(by_node.items()):
            lines.append(f"- Longhorn is moving {len(v)} replica(s) off {n}: {', '.join(sorted(v)[:8])}{' ...' if len(v) > 8 else ''}")
    else:
        lines.append("- Longhorn eviction: none requested")

    prog = prom('max by (pvc_namespace, pvc, rebuild_dst) (longhorn_engine_rebuild_progress) < 100')
    eta = {(e["metric"].get("pvc_namespace"), e["metric"].get("pvc")): float(e["value"][1]) for e in prom(
        '(100 - max by (pvc_namespace, pvc) (longhorn_engine_rebuild_progress)) / '
        '(max by (pvc_namespace, pvc) (deriv(longhorn_engine_rebuild_progress[10m])) * 60 > 0)') if "metric" in e}
    copying = [p for p in prog if "metric" in p]
    if copying:
        lines.append(f"- Copies in progress: {len(copying)}")
        for p in sorted(copying, key=lambda x: float(x["value"][1])):
            key = (p["metric"].get("pvc_namespace"), p["metric"].get("pvc"))
            left = f", ~{eta[key]:.0f} min left" if key in eta else ""
            lines.append(f"  - {key[0]}/{key[1]}: {float(p['value'][1]):.0f}%{left}")
        if eta:
            lines.append(f"  - Longest estimate: ~{max(eta.values()):.0f} min (straight line from the last 10 min)")
    elif prog and "error" in prog[0]:
        lines.append(f"- Copy progress: Prometheus unreachable ({prog[0]['error'][:80]})")
    else:
        lines.append("- Copies in progress: none")

    blocking = [f'{p["metric"]["namespace"]}/{p["metric"]["poddisruptionbudget"]}' for p in prom(
        'max by (namespace, poddisruptionbudget) (kube_poddisruptionbudget_status_pod_disruptions_allowed) == 0')
        if "metric" in p]
    lh_pdbs = [b for b in blocking if b.startswith(LH + "/")]
    other = [b for b in blocking if not b.startswith(LH + "/")]
    lines.append(f"- PDBs at zero disruptions: {len(lh_pdbs)} Longhorn instance-manager"
                 f"{', other: ' + ', '.join(other) if other else ', no others'}")

    machines, err = omni_machines()
    if err:
        lines.append(f"- Omni: not read ({err})")
    else:
        bad = []
        for m in machines:
            s, md = m.get("spec", {}), m.get("metadata", {})
            host = md.get("labels", {}).get("omni.sidero.dev/node-name") or md.get("id")
            stage, apply_s = STAGES.get(s.get("stage", 0), s.get("stage")), APPLY.get(s.get("configapplystatus", 0))
            if stage != "RUNNING" or not s.get("ready") or s.get("lastconfigerror") or apply_s == "FAILED":
                bad.append(f"{host}: {stage}, ready={s.get('ready')}, config {apply_s}"
                           f"{', error: ' + s['lastconfigerror'][:160] if s.get('lastconfigerror') else ''}")
        lines.append(f"- Omni machines: {len(machines)} read, " + ("all RUNNING and ready" if not bad else f"{len(bad)} not ready"))
        lines.extend(f"  - {b}" for b in bad)

    lines.append("")
    lines.append("**What blocks the next reboot**")
    single = {}
    for vname, rs in placed.items():
        if len(rs) == 1:
            single.setdefault(rs[0]["spec"]["nodeID"], []).append(vname)
    for n in sorted(single, key=lambda k: -len(single[k])):
        size = sum(int(vols[v]["status"].get("actualSize") or 0) for v in single[n] if v in vols)
        lines.append(f"- {n}: {len(single[n])} single-copy volume(s), {size / GiB:.0f} GiB to copy on drain")

    disks = []
    for ln in lhnodes:
        for dname, d in (ln["spec"].get("disks") or {}).items():
            if d.get("allowScheduling") and ln["spec"].get("allowScheduling", True):
                disks.append((ln["metadata"]["name"], dname, set(d.get("tags") or []), set(ln["spec"].get("tags") or [])))
    traps = []
    for sc in scs:
        if sc.get("provisioner") != "driver.longhorn.io":
            continue
        p = sc.get("parameters", {})
        want = int(p.get("numberOfReplicas", 3))
        dsel = {t for t in (p.get("diskSelector") or "").split(",") if t}
        nsel = {t for t in (p.get("nodeSelector") or "").split(",") if t}
        hosts = {n for n, _, dt, nt in disks if dsel <= dt and nsel <= nt}
        if (dsel or nsel) and len(hosts) < want:
            traps.append(f'{sc["metadata"]["name"]} wants {want} copies, its selector matches {len(hosts)} node(s)')
    lines.append("- Disk selectors that match too few nodes: " + ("; ".join(traps) if traps else "none"))

    if args.node:
        lines.append("")
        lines.append(f"**If you drain {args.node} now**")
        hit = []
        for vname, rs in placed.items():
            on = [r for r in rs if r["spec"]["nodeID"] == args.node]
            if on and len(rs) - len(on) < 1:
                hit.append(vname)
        size = sum(int(vols[v]["status"].get("actualSize") or 0) for v in hit if v in vols)
        if hit:
            lines.append(f"- Longhorn must copy {len(hit)} volume(s), {size / GiB:.0f} GiB, before the node can go:")
            lines.extend(f"  - {pvc_name(vols[v])} ({int(vols[v]['status'].get('actualSize') or 0) / GiB:.1f} GiB)"
                         for v in sorted(hit, key=lambda v: -int(vols[v]["status"].get("actualSize") or 0))[:15])
        else:
            lines.append("- No volume needs a copy. Every replica on it has another copy elsewhere.")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
