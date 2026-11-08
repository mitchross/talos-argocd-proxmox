# Kanban swarm with full card bodies. Run: cd /opt/hermes && /opt/hermes/.venv/bin/python this.py
# Edit REPO/OUT/RULES/workers/bodies. Swaps the verifier's default auto-fix skill.
import json, sys
sys.path.insert(0, "/opt/hermes")
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import kanban_swarm as ks

REPO = "/path/to/repo"
OUT = "/opt/data/workspace/audits/report.md"
RULES = f"""
## Hard rules
- Repo: {REPO} (commit <sha>). Read-only: no edits, formatting, installs, commits, branches.
- Every finding needs file:line evidence; mark uncertain items "unverified".
- Complete the card with numbered findings (your prefix) in the result.
"""

workers = [
    # profile, title, body, skills
    ks.SwarmWorkerSpec("default", "Area A audit", "Scope... Prefix A." + RULES, ["ponytail-audit"]),
    ks.SwarmWorkerSpec("default", "Area B audit", "Scope... Prefix B." + RULES, ["ponytail-audit"]),
]

with kbc.connect_closing() as conn:
    c = ks.create_swarm(
        conn, goal="<one-line outcome, incl. " + OUT + ">", workers=workers,
        verifier_assignee="default", synthesizer_assignee="default",
        root_title="Swarm: <name>", verifier_title="Verify findings",
        synthesizer_title="Write report", created_by="default",
        workspace_kind="dir", workspace_path=REPO,
        idempotency_key="<unique-key>",
    )
    ctx = ks._swarm_context(c.root_id, "<goal>")
    v_body = "Check each finding against the code; drop unproven ones with a reason; dedupe. Complete with metadata {\"gate\": \"pass\"}." + RULES
    s_body = f"Write ONE report to {OUT} (the only file you may write) from verified findings only." + RULES
    conn.execute("UPDATE tasks SET body=?, skills=? WHERE id=?", (v_body + ctx, json.dumps(["ponytail-review"]), c.verifier_id))
    conn.execute("UPDATE tasks SET body=?, skills=? WHERE id=?", (s_body + ctx, json.dumps(["humanizer"]), c.synthesizer_id))
    conn.commit()
    print(json.dumps(c.as_dict()))
