#!/usr/bin/env python3
"""List Hermes skills on the volume that Git cannot restore.

Run from the talos-argocd-proxmox checkout (needs origin/main fetched):
  python3 skills_drift.py
Compares /opt/data/skills with the image's bundled skills, the Git library
(my-apps/development/hermes/skills/library) and external-skills.txt.
Read-only.
"""
import os
import subprocess

LIB = "my-apps/development/hermes/skills/library"
EXT = "my-apps/development/hermes/scripts/external-skills.txt"
SEEDED = {"devops/homelab-ops"}  # copied by seed.sh from its own ConfigMap


def git(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def skill_dirs(base, rel=True):
    out = set()
    for root, _dirs, files in os.walk(base):
        if "SKILL.md" in files and not any(p in root for p in ("/.hub", "/.archive", ".curator")):
            out.add(os.path.relpath(root, base) if rel else os.path.basename(root))
    return out


vol = skill_dirs("/opt/data/skills")
bundled = skill_dirs("/opt/hermes/skills", rel=False) | skill_dirs("/opt/hermes/optional-skills", rel=False)
lib = {p[len(LIB) + 1:-len("/SKILL.md")] for p in git(f"git ls-tree -r --name-only origin/main {LIB}").split()
       if p.endswith("/SKILL.md")}
ext = set()
for line in git(f"git show origin/main:{EXT}").splitlines():
    parts = line.split()
    if len(parts) == 4 and not line.startswith("#"):
        ext.add(f"{parts[3]}/{os.path.basename(parts[2])}")

missing = sorted(s for s in vol if s not in lib | ext | SEEDED and os.path.basename(s) not in bundled)
diverged = sorted(s for s in lib if os.path.exists(f"/opt/data/skills/{s}/SKILL.md")
                  and open(f"/opt/data/skills/{s}/SKILL.md").read() != git(f"git show origin/main:{LIB}/{s}/SKILL.md"))
print(f"{len(vol)} on volume, {len(lib)} in library, {len(ext)} external")
print("NOT IN GIT:", missing)
print("LIBRARY COPY STALE:", diverged)
