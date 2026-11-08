#!/usr/bin/env python3
"""Restore Git-owned skills without overwriting evolving volume copies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ALIASES = {"pstack/tdd": "pstack/pstack-tdd", "pstack/teach": "pstack/pstack-teach"}


def log(message):
    print(f"[seed] skills: {message}", flush=True)


def skill_path(entry):
    path = str(Path(entry.get("category", "")) / entry["name"])
    return ALIASES.get(path, path)


def copy_missing(source, target):
    for skill in source.rglob("SKILL.md"):
        relative = skill.parent.relative_to(source)
        destination = target / relative
        if (destination / "SKILL.md").exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill.parent, destination, dirs_exist_ok=True)


def restore_last_good(home):
    archive = home / ".skills-last-good.tgz"
    if not archive.exists():
        log("no last-good archive; keeping installed skills and retrying next start")
        return False
    try:
        with tempfile.TemporaryDirectory(dir=home) as temporary:
            root = Path(temporary)
            with tarfile.open(archive) as bundle:
                bundle.extractall(root, filter="data")
            copy_missing(root / "skills", home / "skills")
            saved = root / "skills/.hub/lock.json"
            current = home / "skills/.hub/lock.json"
            if saved.exists():
                lock = json.loads(current.read_text()) if current.exists() else {"version": 1, "installed": {}}
                for name, entry in json.loads(saved.read_text()).get("installed", {}).items():
                    lock.setdefault("installed", {}).setdefault(name, entry)
                current.parent.mkdir(parents=True, exist_ok=True)
                current.write_text(json.dumps(lock, indent=2) + "\n")
        log("registry unreachable, restored last-good")
        return True
    except (OSError, ValueError, tarfile.TarError) as error:
        log(f"last-good restore failed: {error}; keeping installed skills")
        return False


def save_last_good(home):
    temporary = home / ".skills-last-good.tgz.new"
    # Hub quarantine/cache is disposable; keep the lock and installed skill content only.
    def include(member):
        parts = Path(member.name).parts
        if ".hub" in parts and member.name not in ("skills/.hub", "skills/.hub/lock.json"):
            return None
        return member
    with tarfile.open(temporary, "w:gz") as bundle:
        bundle.add(home / "skills", arcname="skills", filter=include)
    temporary.replace(home / ".skills-last-good.tgz")


def external_entries(path):
    return [line.split() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def install_external(entries, home, temporary):
    complete = True
    failed_repositories = set()
    for repo, revision, source, category, *alias in entries:
        destination = home / "skills" / category / (alias[0] if alias else Path(source).name)
        marker = destination / ".source-sha"
        if marker.exists() and marker.read_text().strip() == revision:
            continue
        if (repo, revision) in failed_repositories:
            complete = False
            continue
        try:
            archive = temporary / f"{repo.replace('/', '-')}-{revision}.tgz"
            unpacked = archive.with_suffix("")
            if not unpacked.exists():
                subprocess.run(["curl", "--connect-timeout", "10", "--max-time", "60", "-fsSL", "-o", str(archive),
                                f"https://codeload.github.com/{repo}/tar.gz/{revision}"], check=True)
                unpacked.mkdir()
                with tarfile.open(archive) as bundle:
                    bundle.extractall(unpacked, filter="data")
            roots = list(unpacked.iterdir())
            origin = roots[0] / source
            if not (origin / "SKILL.md").is_file():
                raise ValueError(f"missing SKILL.md: {repo}/{source}")
            staged = temporary / "staged"
            shutil.copytree(origin, staged)
            if alias:
                skill = staged / "SKILL.md"
                text = skill.read_text()
                text = text.replace(f"name: {Path(source).name}\n", f"name: {alias[0]}\n", 1)
                skill.write_text(text)
            (staged / ".source-sha").write_text(revision + "\n")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                shutil.rmtree(destination)
            staged.rename(destination)
        except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
            log(f"external install failed: {repo}/{source}: {error}")
            failed_repositories.add((repo, revision))
            complete = False
    return complete


def normalize_aliases(home):
    lock_path = home / "skills/.hub/lock.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else None
    for source, alias in ALIASES.items():
        original, destination = home / "skills" / source, home / "skills" / alias
        if original.exists() and not destination.exists():
            original.rename(destination)
            skill = destination / "SKILL.md"
            skill.write_text(skill.read_text().replace(f"name: {Path(source).name}\n", f"name: {Path(alias).name}\n", 1))
        if lock and Path(source).name in lock.get("installed", {}) and destination.exists():
            lock["installed"][Path(source).name]["install_path"] = alias
    if lock:
        lock_path.write_text(json.dumps(lock, indent=2) + "\n")


def drift(home, snapshot, external, library, bundled):
    expected = {skill_path(entry) for entry in snapshot.get("skills", [])}
    expected.update(str(Path(row[3]) / (row[4] if len(row) > 4 else Path(row[2]).name)) for row in external)
    for root in (library, bundled):
        if root.exists():
            expected.update(str(skill.parent.relative_to(root)) for skill in root.rglob("SKILL.md"))
    expected.add("devops/homelab-ops")
    actual = {str(skill.parent.relative_to(home / "skills")) for skill in (home / "skills").rglob("SKILL.md")
              if ".hub" not in skill.parts}
    unknown = sorted(actual - expected)
    log("drift (not installed by Git or upstream bundled): " + (", ".join(unknown) if unknown else "none"))
    return unknown


def seed(home, repo, hermes="/opt/hermes/bin/hermes", bundled=Path("/opt/hermes/skills"), offline=False):
    home.mkdir(parents=True, exist_ok=True)
    (home / "skills").mkdir(exist_ok=True)
    snapshot, external, library = {}, [], Path("/nonexistent-skills-library")
    with tempfile.TemporaryDirectory(dir=home) as temporary:
        temporary = Path(temporary)
        try:
            archive = subprocess.run(["git", "-C", str(repo), "archive", "origin/main",
                                      "my-apps/development/hermes/skills", "my-apps/development/hermes/scripts/external-skills.txt"],
                                     check=True, stdout=subprocess.PIPE).stdout
            archive_path = temporary / "git.tar"
            archive_path.write_bytes(archive)
            with tarfile.open(archive_path) as bundle:
                bundle.extractall(temporary, filter="data")
            root = temporary / "my-apps/development/hermes"
            library = root / "skills/library"
            snapshot_path = root / "skills/snapshot.json"
            snapshot = json.loads(snapshot_path.read_text())
            external = external_entries(root / "scripts/external-skills.txt")
            # Restore edited bundled copies before Hermes's CLI can seed stock versions.
            copy_missing(library, home / "skills")
            if offline:
                raise OSError("GitHub fetch failed; registry access skipped")
            pinned_names = {row[4] if len(row) > 4 else Path(row[2]).name for row in external}
            snapshot["skills"] = [entry for entry in snapshot["skills"] if entry["name"] not in pinned_names]
            pending = [entry for entry in snapshot["skills"] if not (home / "skills" / skill_path(entry) / "SKILL.md").exists()]
            complete = True
            if pending:
                pending_path = temporary / "pending.json"
                pending_path.write_text(json.dumps({**snapshot, "skills": pending}))
                environment = {**os.environ, "HERMES_HOME": str(home)}
                result = subprocess.run([hermes, "skills", "snapshot", "import", str(pending_path), "--force"],
                                        stdin=subprocess.DEVNULL, env=environment, timeout=600)
                complete = result.returncode == 0
                if not complete:
                    log(f"partial snapshot import (exit {result.returncode}); continuing with installed skills")
            normalize_aliases(home)
            complete = install_external(external, home, temporary) and complete
            complete = all((home / "skills" / skill_path(entry) / "SKILL.md").exists() for entry in snapshot["skills"]) and complete
            if complete:
                save_last_good(home)
                log("imported from Git snapshot")
            else:
                restore_last_good(home)
        except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
            log(f"Git snapshot unavailable: {error}")
            restore_last_good(home)
        try:
            if snapshot:
                drift(home, snapshot, external, library, bundled)
            else:
                log("drift check unavailable without Git inventory; continuing")
        except Exception as error:
            log(f"drift check failed (informational): {error}")


if __name__ == "__main__":
    try:
        seed(Path(os.environ["HERMES_HOME"]), Path(sys.argv[1]),
             offline=os.environ.get("HERMES_SKILLS_OFFLINE") == "1")
    except Exception as error:
        log(f"seeding failed, keeping installed skills: {error}")
