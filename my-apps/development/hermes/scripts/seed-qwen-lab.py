"""Seed the Qwen Lab profiles from Git (/etc/hermes-qwen-lab). Runs as the hermes user during seed.sh.

Creates each profile once, then rewrites its Git-owned files on every start: config.yaml, SOUL.md,
Hindsight config and lab skills. profile.yaml (Bot Mode roster) is only filled in where keys are
missing, so desktop edits survive. Also creates the qwen-lab Kanban board. The default profile's
files are never written here.
"""
import copy, json, os, subprocess, sys
from pathlib import Path
from io import StringIO

try:  # the Hermes venv ships ruamel, not PyYAML; CI has PyYAML
    from ruamel.yaml import YAML
    _yaml = YAML(typ="safe")
    _yaml.default_flow_style = False
except ImportError:
    _yaml = None
    import yaml as _pyyaml

SRC = Path(os.environ.get("QWEN_LAB_SRC", "/etc/hermes-qwen-lab"))
ROOT = Path(os.environ.get("HERMES_HOME", "/opt/data"))
HERMES = os.environ.get("HERMES_BIN", "/opt/hermes/bin/hermes")
WORKSPACE = Path(os.environ.get("QWEN_LAB_WORKSPACE", "/opt/data/workspace/qwen-lab"))
SANDBOX = WORKSPACE / "sandbox"
BOARD = "qwen-lab"
HINDSIGHT_URL = "http://hindsight-service.hindsight.svc.cluster.local:8888"
# The lab terminal gets the toolchains but not /opt/agents/bin (claude, codex).
LAB_PROFILE_SH = (
    "export PATH=/opt/rust/cargo/bin:/usr/local/go/bin:$PATH\n"
    "export RUSTUP_HOME=/opt/data/tools/rustup RUSTUP_AUTO_INSTALL=1 CARGO_HOME=/opt/data/.cargo\n"
    "export CARGO_BUILD_BUILD_DIR=/opt/scratch/cargo-build/{workspace-path-hash} XDG_CACHE_HOME=/opt/scratch/cache\n"
    "export BUN_INSTALL_CACHE_DIR=/opt/scratch/bun npm_config_cache=/opt/scratch/npm YARN_CACHE_FOLDER=/opt/scratch/yarn\n"
)
GITCONFIG = "[user]\n\tname = Qwen Lab\n\temail = mitchross@users.noreply.github.com\n[init]\n\tdefaultBranch = main\n"


def log(msg):
    print(f"[seed] qwen-lab: {msg}", flush=True)


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def write(path: Path, text: str, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.chmod(mode)
    tmp.replace(path)


def load(text):
    return _yaml.load(text) if _yaml else _pyyaml.safe_load(text)


def dump(data) -> str:
    if not _yaml:
        return _pyyaml.safe_dump(data, sort_keys=False)
    buf = StringIO()
    _yaml.dump(data, buf)
    return buf.getvalue()


def run(*args, check=False):
    r = subprocess.run([HERMES, *args], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        log(f"{' '.join(args[:4])} failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}")
        if check:
            raise RuntimeError(args)
    return r


def seed_profile(name, spec, base, soul, skills_src):
    home = ROOT / "profiles" / name
    if not (home / "config.yaml").exists():
        log(f"creating profile {name}")
        run("profile", "create", name, "--no-skills", "--no-alias", "--description", spec["description"].strip(), check=True)
    cfg = merge(base, spec.get("config"))
    write(home / "config.yaml", "# Git owns this file: my-apps/development/hermes/qwen-lab, seeded on every start.\n" + dump(cfg))
    write(home / "SOUL.md", soul.replace("{role}", spec["role"].strip()))
    hs = cfg["memory"]["hindsight"]
    write(home / "hindsight" / "config.json", json.dumps({
        "mode": hs["mode"], "api_url": hs["api_url"], "bank_id": hs["bank_id"],
        "recall_budget": hs.get("recall_budget", "mid"), "recall_types": "observation,world,experience", "prefetch_retain_drain_timeout": 120,
    }, indent=2) + "\n")

    # Bot Mode roster entry; only missing keys are filled so desktop edits (avatar, section) stay.
    meta_path = home / "profile.yaml"
    meta = (load(meta_path.read_text()) if meta_path.exists() else None) or {}
    meta.setdefault("description", spec["description"].strip())
    bots = meta.setdefault("ui_meta", {}).setdefault("hermes-bots", {})
    for k, v in {"title": spec["title"], "color": spec["color"], "description": spec["description"].strip(),
                 "sectionId": "qwen-lab", "sectionName": "Qwen Lab"}.items():
        bots.setdefault(k, v)
    write(meta_path, dump(meta))

    for skill in spec.get("skills", []):
        write(home / "skills" / "qwen-lab" / skill / "SKILL.md", (skills_src / f"skill-{skill}.md").read_text())

    # Non-secret only: lab profiles never get keys. Multiplexed turns read this, not the pod env.
    write(home / ".env", "# Git owns this file (seed-qwen-lab.py).\nSEARXNG_URL=http://searxng.searxng.svc.cluster.local:8080\n", 0o600)

    term_home = home / "home"
    write(term_home / ".profile", LAB_PROFILE_SH)
    if not (term_home / ".gitconfig").exists():
        write(term_home / ".gitconfig", GITCONFIG)

    if not (home / "plugins" / "hindsight").exists():
        log(f"installing hindsight plugin for {name}")
        run("-p", name, "plugins", "install", "hindsight", "--enable", "--yes-deps")


def seed_board():
    if not (SANDBOX / ".git").exists():
        SANDBOX.mkdir(parents=True, exist_ok=True)
        write(SANDBOX / "README.md", "# Qwen Lab sandbox\n\nScratch repo for lab cards that have no other repo.\n")
        for args in (["init", "-q", "-b", "main"], ["add", "README.md"], ["commit", "-q", "-m", "Start the Qwen Lab sandbox"]):
            subprocess.run(["git", "-C", str(SANDBOX), *args], check=True,
                           env={**os.environ, "GIT_AUTHOR_NAME": "Qwen Lab", "GIT_COMMITTER_NAME": "Qwen Lab",
                                "GIT_AUTHOR_EMAIL": "mitchross@users.noreply.github.com",
                                "GIT_COMMITTER_EMAIL": "mitchross@users.noreply.github.com"})
    boards = run("kanban", "boards", "list").stdout
    if not any(line.split()[:2] and BOARD in line.split()[:2] for line in boards.splitlines()):
        log("creating Kanban board qwen-lab")
        run("kanban", "boards", "create", BOARD, "--name", "Qwen Lab", "--color", "#7c3aed",
            "--description", "Jobs for the local Qwen team (qwen-* profiles).", "--default-workdir", str(SANDBOX))


def main():
    base = load((SRC / "base.yaml").read_text())
    profiles = load((SRC / "profiles.yaml").read_text())
    soul = (SRC / "SOUL.md").read_text()
    failed = 0
    for name, spec in profiles.items():
        try:
            seed_profile(name, spec, base, soul, SRC)
        except Exception as exc:
            failed += 1
            log(f"{name} failed: {exc!r}")
    try:
        seed_board()
    except Exception as exc:
        failed += 1
        log(f"board failed: {exc!r}")
    log(f"done ({len(profiles)} profiles, {failed} errors)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
