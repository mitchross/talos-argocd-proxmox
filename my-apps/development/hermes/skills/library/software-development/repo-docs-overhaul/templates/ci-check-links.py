#!/usr/bin/env python3
"""CI link check: fail if llms.txt or any maintained markdown file links to a repo file that doesn't exist.

Copy to .github/scripts/check-links.py and set REPO below. Pair with a workflow that runs
`python3 .github/scripts/check-links.py` on PRs touching **/*.md or llms.txt.

- llms.txt: every https://github.com/<any-owner>/<REPO>/blob|tree/<BRANCH>/<path> link must exist in the
  checkout (any owner, so forks pass).
- *.md outside SKIP dirs: every relative link target must exist (anchors, external URLs and fenced code
  are ignored).
"""
import pathlib
import re
import sys

REPO = "radar-ng"      # repo name in llms.txt URLs
BRANCH = "master"      # default branch used in llms.txt URLs
ROOT = pathlib.Path(__file__).resolve().parents[2]
SKIP = ("node_modules", ".git", "docs/archive", "target", "/ios/", "/android/")
errors = []

llms = ROOT / "llms.txt"
if llms.exists():
    gh = re.compile(rf"https://github\.com/[^/\s]+/{re.escape(REPO)}/(?:blob|tree)/{re.escape(BRANCH)}/([^)\s#]+)")
    for path in gh.findall(llms.read_text()):
        if not (ROOT / path).exists():
            errors.append(f"llms.txt -> {path}")

link = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
fence = re.compile(r"```.*?```", re.S)
for md in ROOT.rglob("*.md"):
    rel = md.relative_to(ROOT).as_posix()
    if any(s.strip("/") in rel for s in SKIP):
        continue
    text = fence.sub("", md.read_text(errors="ignore"))
    for target in link.findall(text):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        resolved = (ROOT / target.lstrip("/")) if target.startswith("/") else (md.parent / target)
        if not resolved.exists():
            errors.append(f"{rel} -> {target}")

for e in errors:
    print(f"BROKEN {e}")
print(f"{len(errors)} broken link(s)")
sys.exit(1 if errors else 0)
