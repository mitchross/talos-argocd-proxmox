#!/usr/bin/env python3
"""Daily upstream watch for Hermes and Hindsight (no LLM).

Prints only what changed since the last run, and comments the same text on
the tracking issue so GitHub notifies Mitch. Empty output = nothing new.
Add or remove watched upstream fixes in WATCH below.
"""
import json, os, re, subprocess, sys

HOME = os.environ.get("HERMES_HOME", "/opt/data")
STATE = os.path.join(HOME, "state", "upstream-watch.json")
ISSUE_REPO = "mitchross/homelab-images"
ISSUE_TITLE = "Hermes upstream watch"

# (repo, number, why we care)
WATCH = [
    ("NousResearch/hermes-agent", 130718, "s6 kills the gateway 3 s after pod stop (issue #130715)"),
    ("NousResearch/hermes-agent", 135401, "desktop chat turns lost on restart (issue #135286)"),
]


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout.strip()


def gh_api(path):
    return json.loads(sh("gh", "api", path))


def latest_release(repo):
    r = gh_api(f"repos/{repo}/releases/latest")
    return {"tag": r["tag_name"], "date": r["published_at"][:10], "url": r["html_url"]}


def released_in(repo, sha, tag):
    """True when commit sha is already part of release tag."""
    try:
        status = gh_api(f"repos/{repo}/compare/{tag}...{sha}")["status"]
        return status in ("behind", "identical")
    except Exception:
        return False


def collect():
    now = {}
    m = re.search(r"v\d+\.\d+\.\d+", sh("/opt/hermes/bin/hermes", "--version"))
    now["hermes_running"] = m.group(0) if m else "unknown"
    now["hermes_latest"] = latest_release("NousResearch/hermes-agent")
    img = sh("kubectl", "-n", "hindsight", "get", "deploy", "hindsight",
             "-o", "jsonpath={.spec.template.spec.containers[0].image}")
    now["hindsight_running"] = "v" + img.split(":")[-1].split("@")[0].lstrip("v")
    now["hindsight_latest"] = latest_release("vectorize-io/hindsight")
    now["watch"] = {}
    for repo, num, why in WATCH:
        i = gh_api(f"repos/{repo}/issues/{num}")
        merged_at = (i.get("pull_request") or {}).get("merged_at")
        state = "merged" if merged_at else i["state"]
        shipped = None
        if merged_at:
            pr = gh_api(f"repos/{repo}/pulls/{num}")
            tag = now["hermes_latest"]["tag"] if repo.endswith("hermes-agent") else now["hindsight_latest"]["tag"]
            if released_in(repo, pr["merge_commit_sha"], tag):
                shipped = tag
        now["watch"][f"{repo}#{num}"] = {"state": state, "shipped": shipped, "why": why,
                                         "url": i["html_url"], "title": i["title"]}
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
                lines.append(f"- Fix merged, not in a release yet: {w['why']}. {w['url']}")
            elif w["state"] == "closed":
                lines.append(f"- Closed without merging: {w['why']}. {w['url']}")
            elif not old:
                lines.append(f"- Still open: {w['why']}. {w['url']}")
    return lines


def tracking_issue():
    out = sh("gh", "issue", "list", "-R", ISSUE_REPO, "--state", "open", "--search",
             f"{ISSUE_TITLE} in:title", "--json", "number,title")
    for i in json.loads(out or "[]"):
        if i["title"] == ISSUE_TITLE:
            return i["number"]
    return None


def main():
    old = {}
    if os.path.exists(STATE):
        with open(STATE) as f:
            old = json.load(f)
    try:
        now = collect()
    except Exception as e:  # report each new kind of failure once, not daily
        err = f"{type(e).__name__}: {getattr(e, 'stderr', '') or e}"[:300]
        if old.get("last_error") != err:
            old["last_error"] = err
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            with open(STATE, "w") as f:
                json.dump(old, f, indent=1)
            print(f"Upstream watch failed: {err}")
        return
    lines = report(old, now)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(now, f, indent=1)
    if not lines:
        return
    body = "**Hermes upstream watch**\n" + "\n".join(lines)
    if any(now[f"{a}_latest"]["tag"] != now[f"{a}_running"] for a in ("hermes", "hindsight")):
        body += ("\n\nTo upgrade Hermes: merge Renovate's base-image PR in homelab-images, then bump the "
                 "hermes-dev digest in talos `deployment.yaml` and `image-prepull.yaml`.")
    print(body)
    num = tracking_issue()
    if num and "--no-comment" not in sys.argv:
        subprocess.run(["gh", "issue", "comment", str(num), "-R", ISSUE_REPO, "--body", body],
                       capture_output=True, timeout=60)


if __name__ == "__main__":
    main()
