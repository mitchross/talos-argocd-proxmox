#!/usr/bin/env python3
"""Watch upstream Strata for Unsloth Dynamic V3.1 support (no LLM).

Prints a message only when something new shows up; empty output = nothing new.
Signals:
  - setup.py's pinned unsloth/Qwen3.8-Flash-Next-GGUF revision moves off 38bb39e (the Sept V3.0 files)
  - setup.py gains an unsloth UD-Q3_K_XL / UD-IQ3_XXS model entry (sizes new in V3.1)
  - a Strata issue or PR mentioning V3.1 / Dynamic 3.1 appears or changes state
  - #5248 (swap-in engram tables) changes state
Remove this job once V3.1 is supported and benchmarked.
"""
import json, os, re, subprocess

HOME = os.environ.get("HERMES_HOME", "/opt/data")
STATE = os.path.join(HOME, "state", "strata-v31-watch.json")
REPO = "Niko1221/Strata"
OLD_REV = "38bb39ee97821de2c9009abb7e93950eec396e66"


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=True).stdout


def collect():
    now = {}
    setup = sh("gh", "api", f"repos/{REPO}/contents/setup.py", "-H", "Accept: application/vnd.github.raw")
    m = re.search(r'"unsloth/Qwen3\.8-Flash-Next-GGUF":\s*"([0-9a-f]{40})"', setup)
    now["unsloth_rev"] = m.group(1) if m else "missing"
    now["new_sizes"] = sorted(set(re.findall(r'"(UD-Q3_K_XL|UD-IQ3_XXS|UD-Q2_K_XL)":\s*\{', setup)))
    now["head"] = sh("gh", "api", f"repos/{REPO}/commits/main", "--jq", ".sha").strip()[:7]
    found = {}
    pat = re.compile(r"(dynamic|\bUD\b|unsloth)[^\n]{0,40}\bv?3\.1\b|\bv3\.1\b[^\n]{0,40}(unsloth|dynamic|quant)", re.I)
    out = sh("gh", "search", "issues", "--repo", REPO, "unsloth", "--include-prs", "--sort", "updated",
             "--json", "number,title,state,url,body", "--limit", "60")
    for i in json.loads(out or "[]"):
        if pat.search(i["title"] + "\n" + (i.get("body") or "")):
            found[str(i["number"])] = f'{i["state"]} {i["title"]} {i["url"]}'
    e = json.loads(sh("gh", "issue", "view", "5248", "-R", REPO, "--json", "state,url"))
    found["5248"] = f'{e["state"]} engram swap-in tables {e["url"]}'
    now["issues"] = found
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
        return  # first run = baseline, stay quiet
    msgs = []
    if now["unsloth_rev"] != old.get("unsloth_rev"):
        tag = "moved off the Sept V3.0 files" if now["unsloth_rev"] != OLD_REV else "changed"
        msgs.append(f"Strata's pinned Unsloth revision {tag}: {old.get('unsloth_rev','?')[:7]} -> {now['unsloth_rev'][:7]} (upstream head {now['head']}).")
    added = sorted(set(now["new_sizes"]) - set(old.get("new_sizes", [])))
    if added:
        msgs.append(f"Strata setup.py now lists Unsloth sizes: {', '.join(added)}.")
    for n, v in now["issues"].items():
        if old.get("issues", {}).get(n) != v:
            msgs.append(f"Strata #{n}: {v}")
    if msgs:
        text = ("Strata Unsloth V3.1 watch:\n- " + "\n- ".join(msgs) +
                "\n\nNext: ask Hermes to bump Strata in homelab-images (VERSION + SOURCE_REF), then A/B V3.1 "
                "UD-Q3_K_XL / UD-Q4_K_XL vs IQ3_S (compare_models.py + Strata tools/quant_quality.py).")
        print(text)
        # GitHub notifies Mitch; same tracking issue as upstream-watch.py (Strata image lives in homelab-images).
        subprocess.run(["gh", "issue", "comment", "32", "-R", "mitchross/homelab-images", "--body", text],
                       capture_output=True, text=True, timeout=60)


if __name__ == "__main__":
    main()
