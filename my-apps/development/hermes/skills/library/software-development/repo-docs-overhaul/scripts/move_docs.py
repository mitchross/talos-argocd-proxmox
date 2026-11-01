#!/usr/bin/env python3
"""Move docs and rewrite every relative link and path mention.

Usage: move_docs.py map.json [--dry] [--root REPO]
map.json: {"old/path.md": "new/path.md", "old/dir": "new/dir", ...}
Explicit file entries win over a containing dir entry (e.g. move one file out of a dir that is archived).
Operates on --root (default: cwd). Requires a git repo.
"""
import json, os, posixpath, re, subprocess, sys

args = sys.argv[1:]
dry = "--dry" in args
root = args[args.index("--root") + 1] if "--root" in args else os.getcwd()
mapfile = os.path.abspath([a for a in args if a.endswith(".json")][0])
MOVES = json.load(open(mapfile))
os.chdir(root)

def tracked():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\n") if f]

files_explicit = {o: n for o, n in MOVES.items() if os.path.isfile(o)}
dirs = {o: n for o, n in MOVES.items() if o not in files_explicit}
fmap = {}
for f in tracked():
    if f in files_explicit:
        fmap[f] = files_explicit[f]; continue
    for old, new in sorted(dirs.items(), key=lambda x: -len(x[0])):
        if f.startswith(old + "/"):
            fmap[f] = new + f[len(old):]; break

if dry:
    for k, v in sorted(fmap.items()):
        print(f"{k} -> {v}")
    sys.exit()

for old, new in sorted(fmap.items()):
    os.makedirs(os.path.dirname(new) or ".", exist_ok=True)
    subprocess.run(["git", "mv", old, new], check=True)
for d in sorted(dirs, key=len, reverse=True):
    if os.path.isdir(d) and not os.listdir(d):
        os.rmdir(d)

inv = {v: k for k, v in fmap.items()}

def map_path(p):
    p = p.rstrip("/")
    if p in fmap:
        return fmap[p]
    for old, new in sorted(dirs.items(), key=lambda x: -len(x[0])):
        if p == old or p.startswith(old + "/"):
            return new + p[len(old):]
    return p

LINK = re.compile(r"(\]\()([^)\s]+)(\))|(<img[^>]*?src=\")([^\"]+)(\")|(^\[[^\]]+\]:\s*)(\S+)()", re.M)
changed = set()
for new_file in [f for f in tracked() if f.endswith(".md") and "node_modules" not in f]:
    old_file = inv.get(new_file, new_file)
    old_dir, new_dir = posixpath.dirname(old_file), posixpath.dirname(new_file)
    text = open(new_file, encoding="utf-8").read()

    def fix(t):
        if re.match(r"^[a-z]+:", t) or t.startswith(("#", "/")):
            return t
        path, frag = (t.split("#", 1) + [""])[:2]
        if not path:
            return t
        old_abs = posixpath.normpath(posixpath.join(old_dir, path))
        if old_abs.startswith(".."):
            return t
        rel = posixpath.relpath(map_path(old_abs), new_dir or ".")
        if path.endswith("/") and not rel.endswith("/"):
            rel += "/"
        return rel + ("#" + frag if frag else "")

    def repl(m):
        if m.group(1):
            return m.group(1) + fix(m.group(2)) + m.group(3)
        if m.group(4):
            return m.group(4) + fix(m.group(5)) + m.group(6)
        return m.group(7) + fix(m.group(8))

    out = LINK.sub(repl, text)
    if out != text:
        open(new_file, "w", encoding="utf-8").write(out); changed.add(new_file)

# Bare repo-root path mentions (code comments, backticks, llms.txt) and blob URLs.
# Archived files are skipped: their links were fixed above, their prose is history.
mentions = sorted(((o, n) for o, n in fmap.items() if o.endswith(".md")), key=lambda x: -len(x[0]))
exts = re.compile(r"\.(md|txt|ts|tsx|js|jsx|rs|py|go|sh|swift|kt|yml|yaml|json|toml)$|(^|/)\.env")
for f in tracked():
    if not exts.search(f) or "node_modules" in f or "/archive/" in f or not os.path.isfile(f):
        continue
    try:
        t = open(f, encoding="utf-8").read()
    except UnicodeDecodeError:
        continue
    o = t
    for old, new in mentions:
        t = re.sub(rf"(/blob/[\w.-]+/){re.escape(old)}", lambda m: m.group(1) + new, t)
        t = re.sub(rf"(?<![\w/.(-]){re.escape(old)}", lambda m: new, t)
    if t != o:
        open(f, "w", encoding="utf-8").write(t); changed.add(f)

print(f"moved {len(fmap)} files; rewrote {len(changed)} files")
for c in sorted(changed):
    print("  ", c)
