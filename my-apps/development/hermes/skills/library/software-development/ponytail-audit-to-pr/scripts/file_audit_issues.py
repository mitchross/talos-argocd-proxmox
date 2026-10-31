#!/usr/bin/env python3
"""File a Ponytail audit report as a GitHub epic + fix-first issues.

Report format: '## Must|Should|Nice' groups, findings as '### <ID>. <title>'
followed by '- Files/Why/Change/Lines saved' bullets.

Usage:
  file_audit_issues.py --repo owner/name --report path.md --sha abc1234 \
      [--must] [--fix-first C1,F2,B1,F1] [--hold F1] [--label ponytail-audit] \
      [--epic-title "Ponytail audit 2026-10"] [--dry-run]
"""
import argparse, json, re, subprocess, sys


def gh(*a, dry=False):
    if dry:
        print("DRY gh", " ".join(a[:4]), "...")
        return "https://github.com/x/y/issues/0"
    return subprocess.run(["gh", *a], check=True, capture_output=True, text=True).stdout.strip()


def parse(report):
    items, group = [], None
    for line in open(report).read().splitlines():
        if line.startswith("## "):
            group = line[3:].strip()
            continue
        m = re.match(r"^### (\w+)\. (.+)$", line)
        if m:
            items.append({"id": m.group(1), "title": m.group(2), "group": group, "body": []})
        elif items:
            items[-1]["body"].append(line)
    return items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--fix-first", default="")
    p.add_argument("--must", action="store_true", help="also file an issue for every Must finding")
    p.add_argument("--hold", default="", help="ids filed as issues but waiting on a user decision")
    p.add_argument("--label", default="ponytail-audit")
    p.add_argument("--epic-title", default="Ponytail audit")
    p.add_argument("--epic", type=int, help="existing epic number: add issues to it instead of creating one")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    d = a.dry_run

    items = [i for i in parse(a.report) if i["group"] in ("Must", "Should", "Nice")]
    byid = {i["id"]: i for i in items}
    fix = [x for x in a.fix_first.split(",") if x]
    if a.must:
        fix = [i["id"] for i in items if i["group"] == "Must" and i["id"] not in fix] + fix
    hold = set(x for x in a.hold.split(",") if x)
    missing = [x for x in fix if x not in byid]
    if missing:
        sys.exit(f"ids not in report: {missing}")
    counts = {g: sum(1 for i in items if i["group"] == g) for g in ("Must", "Should", "Nice")}
    print("findings:", len(items), counts)

    if not d:
        subprocess.run(["gh", "label", "create", a.label, "-R", a.repo, "--color", "c5def5",
                        "--description", "Findings from a Ponytail audit"], capture_output=True)

    urls = {}
    for fid in fix:
        it = byid[fid]
        crit = (["User decides the approach before work starts."] if fid in hold else []) + [
            "The change described above is made, and nothing else.",
            "The repo's AGENTS.md gates pass for the touched areas."]
        body = (f"From the Ponytail audit of `{a.sha}` (finding **{fid}**, {it['group']}).\n\n"
                f"## What to build\n\n" + "\n".join(it["body"]).strip() +
                "\n\n## Acceptance criteria\n\n" + "\n".join(f"- [ ] {c}" for c in crit) +
                "\n\n## Blocked by\n\nNone (can start immediately).")
        urls[fid] = gh("issue", "create", "-R", a.repo, "--title", f"{fid}: {it['title']}",
                       "--body", body, "--label", a.label, dry=d)
        print(fid, urls[fid])

    if a.epic:
        enum = str(a.epic)
        epic = f"https://github.com/{a.repo}/issues/{enum}"
        if not d:
            body = gh("issue", "view", enum, "-R", a.repo, "--json", "body", "--jq", ".body")
            missing = [i for i in items if f"**{i['id']}**" not in body]
            if missing:  # a follow-up report: append its checklist as a new section
                sec = ["", f"## Follow-up audit (`{a.sha}`): {len(items)} findings", ""]
                for g in ("Must", "Should", "Nice"):
                    gi = [i for i in missing if i["group"] == g]
                    if gi:
                        sec += [f"### {g}"] + [f"- [ ] **{i['id']}**: {i['title']}" for i in gi] + [""]
                body += "\n".join(sec)
            for fid, u in urls.items():
                n = u.rsplit("/", 1)[1]
                body = re.sub(rf"^(- \[ \] \*\*{fid}\*\*: .*?)$", rf"\1 (#{n})", body, count=1, flags=re.M)
            gh("issue", "edit", enum, "-R", a.repo, "--body", body)
            if missing:
                gh("issue", "comment", enum, "-R", a.repo, "--body-file", a.report)
    else:
        lines = [f"Ponytail audit of `{a.sha}`. {len(items)} verified findings: "
                 f"{counts['Must']} Must, {counts['Should']} Should, {counts['Nice']} Nice.", ""]
        for g in ("Must", "Should", "Nice"):
            lines.append(f"## {g}")
            gi = [i for i in items if i["group"] == g]
            lines += [f"- [ ] **{i['id']}**: {i['title']}" +
                      (f" (#{urls[i['id']].rsplit('/', 1)[1]})" if i["id"] in urls else "")
                      for i in gi] or ["None."]
            lines.append("")
        lines.append("The full report with file and line refs is in the first comment.")
        epic = gh("issue", "create", "-R", a.repo, "--title", a.epic_title, "--body", "\n".join(lines),
                  "--label", a.label, dry=d)
        enum = epic.rsplit("/", 1)[1]
        if not d:
            gh("issue", "comment", epic, "--body-file", a.report)
    print("EPIC", epic)
    if not d:
        for fid, u in urls.items():
            n = u.rsplit("/", 1)[1]
            iid = gh("api", f"repos/{a.repo}/issues/{n}", "--jq", ".id")
            gh("api", "-X", "POST", f"repos/{a.repo}/issues/{enum}/sub_issues", "-F", f"sub_issue_id={iid}")
    print(json.dumps({"epic": epic, **urls}))


if __name__ == "__main__":
    main()
