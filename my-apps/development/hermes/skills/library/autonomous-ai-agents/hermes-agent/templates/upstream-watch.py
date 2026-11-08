#!/usr/bin/env python3
"""Daily upstream watch for a self-hosted Hermes (+ Hindsight). No LLM.

Run as a no_agent cron job: cronjob(action='create', schedule='every day at 9am',
script='upstream-watch.py', no_agent=True, name='upstream-watch').
Copy to $HERMES_HOME/scripts/ and edit ISSUE_REPO, WATCH and the version probes.

Prints only what changed since the last run (empty = silent tick) and comments the
same text on a GitHub tracking issue, so GitHub notifies the user's phone.
A watched PR counts as "shipped" when its merge commit is already in the latest
release tag (compare API status behind/identical).
"""
import json, os, re, subprocess, sys

HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
STATE = os.path.join(HOME, "state", "upstream-watch.json")
ISSUE_REPO = "OWNER/REPO"          # repo holding an open issue titled ISSUE_TITLE
ISSUE_TITLE = "Hermes upstream watch"
WATCH = [  # (repo, PR or issue number, why we care)
    # ("NousResearch/hermes-agent", 12345, "short reason"),
]


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout.strip()


def gh_api(path):
    return json.loads(sh("gh", "api", path))


def latest_release(repo):
    r = gh_api(f"repos/{repo}/releases/latest")
    return {"tag": r["tag_name"], "date": r["published_at"][:10], "url": r["html_url"]}


def released_in(repo, sha, tag):
    try:
        return gh_api(f"repos/{repo}/compare/{tag}...{sha}")["status"] in ("behind", "identical")
    except Exception:
        return False


def collect():
    now = {}
    m = re.search(r"v\d+\.\d+\.\d+", sh("hermes", "--version"))
    now["hermes_running"] = m.group(0) if m else "unknown"
    now["hermes_latest"] = latest_release("NousResearch/hermes-agent")
    # Hindsight in k8s (drop if not used):
    img = sh("kubectl", "-n", "hindsight", "get", "deploy", "hindsight",
             "-o", "jsonpath={.spec.template.spec.containers[0].image}")
    now["hindsight_running"] = "v" + img.split(":")[-1].split("@")[0].lstrip("v")
    now["hindsight_latest"] = latest_release("vectorize-io/hindsight")
    now["watch"] = {}
    for repo, num, why in WATCH:
        i = gh_api(f"repos/{repo}/issues/{num}")
        merged_at = (i.get("pull_request") or {}).get("merged_at")
        state, shipped = ("merged" if merged_at else i["state"]), None
        if merged_at:
            sha = gh_api(f"repos/{repo}/pulls/{num}")["merge_commit_sha"]
            if released_in(repo, sha, latest_release(repo)["tag"]):
                shipped = latest_release(repo)["tag"]
        now["watch"][f"{repo}#{num}"] = {"state": state, "shipped": shipped, "why": why, "url": i["html_url"]}
    return now


def report(old, now):
    lines = []
    for app in ("hermes", "hindsight"):
        lat, run = now[f"{app}_latest"], now[f"{app}_running"]
        if old.get(f"{app}_latest", {}).get("tag") != lat["tag"] or old.get(f"{app}_running") != run:
            if lat["tag"] != run:
                lines.append(f"- **{app.title()} {lat['tag']}** is out ({lat['date']}); you run {run}. {lat['url']}")
            elif old:
                lines.append(f"- {app.title()} is up to date ({run}).")
    for key, w in now["watch"].items():
        o = old.get("watch", {}).get(key, {})
        if o.get("state") != w["state"] or o.get("shipped") != w["shipped"]:
            if w["shipped"]:
                lines.append(f"- Fix shipped in **{w['shipped']}**: {w['why']}. {w['url']}")
            elif w["state"] == "merged":
                lines.append(f"- Fix merged, not released yet: {w['why']}. {w['url']}")
            elif w["state"] == "closed":
                lines.append(f"- Closed without merging: {w['why']}. {w['url']}")
            elif not old:
                lines.append(f"- Still open: {w['why']}. {w['url']}")
    return lines


def tracking_issue():
    out = sh("gh", "issue", "list", "-R", ISSUE_REPO, "--state", "open", "--search",
             f"{ISSUE_TITLE} in:title", "--json", "number,title")
    return next((i["number"] for i in json.loads(out or "[]") if i["title"] == ISSUE_TITLE), None)


def save(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(d, f, indent=1)


def main():
    old = json.load(open(STATE)) if os.path.exists(STATE) else {}
    try:
        now = collect()
    except Exception as e:  # report each new failure once, not every day
        err = f"{type(e).__name__}: {getattr(e, 'stderr', '') or e}"[:300]
        if old.get("last_error") != err:
            old["last_error"] = err
            save(old)
            print(f"Upstream watch failed: {err}")
        return
    lines = report(old, now)
    save(now)
    if not lines:
        return
    body = "**Hermes upstream watch**\n" + "\n".join(lines)
    print(body)
    num = tracking_issue()
    if num and "--no-comment" not in sys.argv:
        subprocess.run(["gh", "issue", "comment", str(num), "-R", ISSUE_REPO, "--body", body],
                       capture_output=True, timeout=60)


if __name__ == "__main__":
    main()
