#!/usr/bin/env python3
"""Check relative links and <img src> in tracked markdown. Usage: check_links.py [repo_root]
Stage new files first (git add -A): only tracked files are scanned. Exit 1 if anything is broken."""
import os, posixpath, re, subprocess, sys

os.chdir(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
files = [f for f in subprocess.run(["git", "ls-files", "*.md"], capture_output=True, text=True).stdout.split()
         if "node_modules" not in f]
bad = 0
for f in files:
    t = re.sub(r"```.*?```", "", open(f, encoding="utf-8").read(), flags=re.S)
    for m in re.finditer(r"\]\(([^)\s]+)\)|<img[^>]*?src=\"([^\"]+)\"", t):
        tgt = m.group(1) or m.group(2)
        if re.match(r"^[a-z]+:", tgt) or tgt.startswith(("#", "/")):
            continue
        p = tgt.split("#")[0]
        if p and not os.path.exists(posixpath.normpath(posixpath.join(posixpath.dirname(f), p))):
            bad += 1
            print(f"BROKEN {f}: {tgt}")
print(f"broken: {bad}  files: {len(files)}")
sys.exit(1 if bad else 0)
