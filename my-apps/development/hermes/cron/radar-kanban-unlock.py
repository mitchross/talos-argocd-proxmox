#!/usr/bin/env python3
# Completes blocked radar-ng Kanban cards once the PR named in their block reason is merged, then dispatches.
import json, re, subprocess

H = "/opt/hermes/bin/hermes"
run = lambda *a: subprocess.run(a, capture_output=True, text=True, timeout=120)

out = []
for c in json.loads(run(H, "kanban", "list", "--status", "running", "--json").stdout or "[]"):
    if not c["title"].startswith("radar-ng"):
        continue
    d = json.loads(run(H, "kanban", "show", c["id"], "--json").stdout)
    last = d["events"][-1] if d["events"] else {}
    if last.get("kind") == "worker_result" and not (d["runs"] and d["runs"][-1].get("pid")):
        run(H, "kanban", "reclaim", c["id"], "--reason", "worker exited but card stayed running (pod restart)")
        out.append(f"{c['id']} {c['title']}: dead worker reclaimed")
cards = []
for status in ("blocked", "review"):
    cards += json.loads(run(H, "kanban", "list", "--status", status, "--json").stdout or "[]")
for c in cards:
    if not c["title"].startswith("radar-ng"):
        continue
    d = json.loads(run(H, "kanban", "show", c["id"], "--json").stdout)
    blocks = [e for e in d["events"] if e.get("kind") == "blocked"]
    reason = (blocks[-1]["payload"].get("reason") or "") if blocks else ""
    reason += " " + (d.get("latest_summary") or "")
    m = re.search(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", reason)
    if not m:
        continue
    state = run("gh", "pr", "view", m.group(2), "-R", m.group(1), "--json", "state", "-q", ".state").stdout.strip()
    if state == "MERGED":
        r = run(H, "kanban", "complete", c["id"], "--summary", f"PR {m.group(0)} merged by Mitch")
        out.append(f"{c['id']} {c['title']}: PR merged -> completed ({r.returncode})")

if out:
    d = run(H, "kanban", "dispatch", "--max", "3")
    out.append("dispatch: " + " ".join(l.strip() for l in d.stdout.splitlines() if "->" in l or "Spawned" in l))
    print("\n".join(out))
