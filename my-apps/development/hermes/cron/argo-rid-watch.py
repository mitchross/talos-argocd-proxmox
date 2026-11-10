#!/usr/bin/env python3
"""Watch Argo CD's RespectIgnoreDifferences fix (no LLM).

Prints only when something changes; empty output = nothing new.
Signals:
  - argo-cd PR #30675 (rebuild RID apply target from ignore rules) changes state or merges
  - issues #30674 / #26588 change state
  - once #30675 is merged: the first release tag that contains its merge commit
Comments on talos-argocd-proxmox#3503 so GitHub notifies Mitch.
Remove this job once Argo runs a release with the fix and #3503 is closed.
"""
import json, os, subprocess

HOME = os.environ.get("HERMES_HOME", "/opt/data")
STATE = os.path.join(HOME, "state", "argo-rid-watch.json")
REPO = "argoproj/argo-cd"
ISSUE = ("3503", "mitchross/talos-argocd-proxmox")


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=True).stdout


def released_in(sha):
    """Newest-first release tags whose commit contains sha."""
    tags = json.loads(sh("gh", "api", f"repos/{REPO}/releases?per_page=15", "--jq", "[.[].tag_name]"))
    hits = []
    for t in tags:
        st = sh("gh", "api", f"repos/{REPO}/compare/{sha}...{t}", "--jq", ".status").strip()
        if st in ("ahead", "identical"):
            hits.append(t)
    return hits


def collect():
    now = {}
    pr = json.loads(sh("gh", "pr", "view", "30675", "-R", REPO, "--json", "state,mergeCommit,url"))
    now["pr30675"] = pr["state"]
    sha = (pr.get("mergeCommit") or {}).get("oid")
    for n in ("30674", "26588"):
        now[f"issue{n}"] = json.loads(sh("gh", "issue", "view", n, "-R", REPO, "--json", "state"))["state"]
    now["released_in"] = released_in(sha) if sha else []
    return now


def main():
    now = collect()
    try:
        old = json.load(open(STATE))
    except Exception:
        old = None
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(now, open(STATE, "w"), indent=1)
    if old is None:
        return  # first run = baseline
    msgs = []
    for k in ("pr30675", "issue30674", "issue26588"):
        if now[k] != old.get(k):
            num = k.replace("pr", "").replace("issue", "")
            msgs.append(f"argo-cd #{num}: {old.get(k)} -> {now[k]} https://github.com/{REPO}/issues/{num}")
    new_tags = [t for t in now["released_in"] if t not in old.get("released_in", [])]
    if new_tags:
        msgs.append(f"The RID fix (#30675) is in release(s): {', '.join(new_tags)}")
    if msgs:
        text = ("Argo RespectIgnoreDifferences watch:\n- " + "\n- ".join(msgs) +
                "\n\nNext: once a release has the fix, ask Hermes to bump Argo, then re-enable "
                "RespectIgnoreDifferences in the my-apps AppSet (see the checklist above).")
        print(text)
        subprocess.run(["gh", "issue", "comment", ISSUE[0], "-R", ISSUE[1], "--body", text],
                       capture_output=True, text=True, timeout=60)


if __name__ == "__main__":
    main()
