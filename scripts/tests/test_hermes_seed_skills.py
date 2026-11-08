"""Skill recovery uses only a disposable home and local Git fixture."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / "my-apps/development/hermes/scripts/seed-skills.py"
spec = importlib.util.spec_from_file_location("seed_skills", MODULE)
seed_skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_skills)


def put_skill(root, relative, text="original"):
    path = root / relative / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def repository(tmp_path, skills=None, external=""):
    repo = tmp_path / "repo"
    root = repo / "my-apps/development/hermes"
    (root / "skills").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "skills/snapshot.json").write_text(json.dumps({"skills": skills or [], "taps": []}))
    (root / "scripts/external-skills.txt").write_text(external)
    put_skill(root / "skills/library", "devops/local")
    for args in (["init", "-q", str(repo)], ["-C", str(repo), "add", "."],
                 ["-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-qm", "fixture"],
                 ["-C", str(repo), "update-ref", "refs/remotes/origin/main", "HEAD"]):
        subprocess.run(["git", *args], check=True)
    return repo


def test_git_library_and_cache_are_missing_only(tmp_path, capsys):
    repo = repository(tmp_path)
    home = tmp_path / "h"
    existing = put_skill(home / "skills", "devops/local", "edited")
    seed_skills.seed(home, repo, bundled=tmp_path / "bundled")
    assert existing.read_text() == "edited"
    assert (home / ".skills-last-good.tgz").exists()
    assert "imported from Git snapshot" in capsys.readouterr().out


def test_github_and_registry_down_restores_cache(tmp_path, capsys):
    home = tmp_path / "h"
    put_skill(home / "skills", "media/keep")
    put_skill(home / "skills", "media/edited")
    lock = home / "skills/.hub/lock.json"
    lock.parent.mkdir()
    lock.write_text(json.dumps({"version": 1, "installed": {"keep": {"install_path": "media/keep"}}}))
    seed_skills.save_last_good(home)
    (home / "skills/media/keep/SKILL.md").unlink()
    edited = home / "skills/media/edited/SKILL.md"
    edited.write_text("user changes")
    lock.unlink()
    seed_skills.seed(home, tmp_path / "missing-repo", bundled=tmp_path / "bundled")
    assert (home / "skills/media/keep/SKILL.md").read_text() == "original"
    assert edited.read_text() == "user changes"
    assert "keep" in json.loads(lock.read_text())["installed"]
    assert "registry unreachable, restored last-good" in capsys.readouterr().out


def test_registry_failure_keeps_last_good(tmp_path, capsys):
    repo = repository(tmp_path, [{"name": "remote", "category": "media", "identifier": "official/media/remote"}])
    home = tmp_path / "h"
    put_skill(home / "skills", "media/recover")
    seed_skills.save_last_good(home)
    original = (home / ".skills-last-good.tgz").read_bytes()
    (home / "skills/media/recover/SKILL.md").unlink()
    seed_skills.seed(home, repo, hermes="/bin/false", bundled=tmp_path / "bundled")
    assert (home / "skills/media/recover/SKILL.md").exists()
    assert (home / ".skills-last-good.tgz").read_bytes() == original
    assert "restored last-good" in capsys.readouterr().out


def test_false_success_import_does_not_replace_cache(tmp_path, capsys):
    repo = repository(tmp_path, [{"name": "absent", "category": "media", "identifier": "official/media/absent"}])
    seed_skills.seed(tmp_path / "h", repo, hermes="/bin/true", bundled=tmp_path / "bundled")
    assert not (tmp_path / "h/.skills-last-good.tgz").exists()
    assert "no last-good archive" in capsys.readouterr().out


def test_warm_start_does_not_fetch_registry(tmp_path):
    repo = repository(tmp_path, [{"name": "present", "category": "media", "identifier": "official/media/present"}])
    home = tmp_path / "h"
    put_skill(home / "skills", "media/present", "user changes")
    seed_skills.seed(home, repo, hermes="/nonexistent-hermes", bundled=tmp_path / "bundled")
    assert (home / ".skills-last-good.tgz").exists()


def test_snapshot_skips_pinned_names_across_categories_and_aliases(tmp_path):
    entries = [{"name": name, "category": "media", "identifier": f"official/media/{name}"}
               for name in ["pinned", "renamed", "remote"]]
    external = "owner/repo sha skills/pinned devops\nowner/repo sha skills/original devops renamed\n"
    repo = repository(tmp_path, entries, external)
    home = tmp_path / "h"
    run = subprocess.run
    imported = []

    def import_snapshot(command, **kwargs):
        if command[0] != "fake-hermes":
            return run(command, **kwargs)
        assert kwargs["env"]["HERMES_HOME"] == str(home)
        pending = json.loads(Path(command[4]).read_text())["skills"]
        imported.extend(entry["name"] for entry in pending)
        for entry in pending:
            put_skill(home / "skills", seed_skills.skill_path(entry))
        return subprocess.CompletedProcess(command, 0)

    def install_pins(entries, home, temporary):
        for row in entries:
            put_skill(home / "skills", f"{row[3]}/{row[4] if len(row) > 4 else Path(row[2]).name}")
        return True

    with patch.object(seed_skills.subprocess, "run", side_effect=import_snapshot), \
            patch.object(seed_skills, "install_external", side_effect=install_pins):
        seed_skills.seed(home, repo, hermes="fake-hermes", bundled=tmp_path / "bundled")
    assert imported == ["remote"]
    assert (home / ".skills-last-good.tgz").exists()
    assert not (home / "skills/media/pinned/SKILL.md").exists()
    assert not (home / "skills/media/renamed/SKILL.md").exists()


def test_aliases_preserve_both_tdd_skills(tmp_path):
    home = tmp_path / "h"
    put_skill(home / "skills", "pstack/tdd", "---\nname: tdd\n---\n")
    matt = put_skill(home / "skills", "software-development/tdd", "Matt")
    lock = home / "skills/.hub/lock.json"
    lock.parent.mkdir()
    lock.write_text(json.dumps({"installed": {"tdd": {"install_path": "pstack/tdd"}}}))
    seed_skills.normalize_aliases(home)
    assert "name: pstack-tdd" in (home / "skills/pstack/pstack-tdd/SKILL.md").read_text()
    assert matt.read_text() == "Matt"
    assert json.loads(lock.read_text())["installed"]["tdd"]["install_path"] == "pstack/pstack-tdd"


def test_drift_uses_git_sources_not_volume_lock(tmp_path):
    home = tmp_path / "h"
    for name in ["media/snapshot", "devops/pinned", "devops/library", "media/bundled", "media/untracked"]:
        put_skill(home / "skills", name)
    library, bundled = tmp_path / "library", tmp_path / "bundled"
    put_skill(library, "devops/library")
    put_skill(bundled, "media/bundled")
    assert seed_skills.drift(home, {"skills": [{"name": "snapshot", "category": "media"}]},
                             [["owner/repo", "sha", "skills/pinned", "devops"]], library, bundled) == ["media/untracked"]


def test_corrupt_cache_is_nonfatal(tmp_path, capsys):
    home = tmp_path / "h"
    home.mkdir()
    (home / ".skills-last-good.tgz").write_text("broken")
    seed_skills.seed(home, tmp_path / "missing")
    assert "last-good restore failed" in capsys.readouterr().out


def test_external_failure_fetches_repo_once(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    entries = [["owner/repo", "sha", f"skills/{name}", "media"] for name in ["one", "two"]]
    with patch.object(seed_skills.subprocess, "run", side_effect=subprocess.CalledProcessError(7, "curl")) as run:
        assert not seed_skills.install_external(entries, home, tmp_path)
        assert run.call_count == 1


def test_drift_error_is_nonfatal(tmp_path, capsys):
    repo = repository(tmp_path)
    with patch.object(seed_skills, "drift", side_effect=OSError("denied")):
        seed_skills.seed(tmp_path / "h", repo)
    assert "drift check failed (informational)" in capsys.readouterr().out


def test_archive_omits_quarantine(tmp_path):
    home = tmp_path / "h"
    put_skill(home / "skills", "media/real")
    put_skill(home / "skills", ".hub/quarantine/unused")
    seed_skills.save_last_good(home)
    with tarfile.open(home / ".skills-last-good.tgz") as bundle:
        names = bundle.getnames()
    assert "skills/media/real/SKILL.md" in names
    assert not any("quarantine" in name for name in names)
