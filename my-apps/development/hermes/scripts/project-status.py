#!/usr/bin/env python3
"""Print one registered project's live status: Kanban cards and open GitHub PRs.

`project-status.py <slug>` prints text. `--hook` reads a pre_llm_call payload and adds the status to a chat's first turn.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

OPEN_STATUSES = ("running", "review", "blocked", "ready", "todo", "triage", "scheduled")
SKIP_SOURCES = {"kanban", "cron"}
DEFAULT_BRANCHES = {"main", "master"}
DONE_LIMIT = 5
PR_LIMIT = 30


def hermes_home():
    return Path(os.environ.get("HERMES_HOME", "/opt/data"))


def _rows(db_path, sql, params=()):
    # Read-only: a status read must never create or lock a live database.
    if not db_path.exists():
        return []
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params)]


def load_projects(home):
    projects = _rows(home / "projects.db", "SELECT id, slug, name, board_slug, primary_path FROM projects WHERE archived = 0")
    folders = _rows(home / "projects.db", "SELECT project_id, path FROM project_folders")
    for project in projects:
        paths = [f["path"] for f in folders if f["project_id"] == project["id"]]
        project["folders"] = [p for p in [project["primary_path"], *paths] if p]
    return projects


def load_extras(path):
    """slug -> {repo, plan} from the Git-owned project list (slug|name|path|repo|plan)."""
    extras = {}
    if not path.exists():
        return extras
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        slug, _name, _path, repo, plan = (line.split("|") + [""] * 5)[:5]
        extras[slug.strip()] = {"repo": repo.strip(), "plan": plan.strip()}
    return extras


def project_for_path(projects, path):
    """The project whose folder is the longest ancestor of path, as upstream project_for_path does."""
    if not path:
        return None
    target, best, best_len = Path(path), None, -1
    for project in projects:
        for folder in project["folders"]:
            root = Path(folder)
            if (target == root or root in target.parents) and len(root.parts) > best_len:
                best, best_len = project, len(root.parts)
    return best


def projects_named(projects, text):
    """Projects whose name or slug is a whole word in text; separators are optional."""
    found = []
    for project in projects:
        for label in (project["name"], project["slug"]):
            parts = [re.escape(p) for p in re.split(r"[-_\s]+", label.lower()) if p]
            if parts and re.search(r"(?<![\w-])" + r"[-_\s]?".join(parts) + r"(?![\w-])", text.lower()):
                found.append(project)
                break
    return found


def board_db(home, board_slug):
    if not board_slug or board_slug == "default":
        return home / "kanban.db"
    return home / "kanban" / "boards" / board_slug / "kanban.db"


def load_cards(home, project):
    """Open and recently done cards of one project only."""
    db = board_db(home, project["board_slug"])
    # A board bound to the project holds only its cards; a shared board is filtered by link or title prefix.
    where, params = "1 = 1", []
    if not project["board_slug"]:
        where, params = "(project_id = ? OR lower(title) LIKE ?)", [project["id"], project["slug"].lower() + "%"]
    marks = ",".join("?" * len(OPEN_STATUSES))
    cards = _rows(db, f"SELECT id, title, status, assignee, branch_name FROM tasks WHERE {where} AND status IN ({marks}) "
                  "ORDER BY created_at", [*params, *OPEN_STATUSES])
    for card in cards:
        blocked = _rows(db, "SELECT payload FROM task_events WHERE task_id = ? AND kind = 'blocked' ORDER BY id DESC LIMIT 1",
                        [card["id"]])
        card["reason"] = ""
        if card["status"] == "blocked" and blocked:
            try:
                card["reason"] = json.loads(blocked[0]["payload"] or "{}").get("reason") or ""
            except ValueError:
                pass
        note = _rows(db, "SELECT author, body FROM task_comments WHERE task_id = ? ORDER BY id DESC LIMIT 1", [card["id"]])
        card["note"] = f"{note[0]['author']}: {note[0]['body']}" if note else ""
    done = _rows(db, f"SELECT id, title, completed_at, result FROM tasks WHERE {where} AND status = 'done' "
                 "ORDER BY completed_at DESC LIMIT ?", [*params, DONE_LIMIT])
    for card in done:
        run = _rows(db, "SELECT summary FROM task_runs WHERE task_id = ? AND summary IS NOT NULL ORDER BY id DESC LIMIT 1",
                    [card["id"]])
        card["summary"] = (run[0]["summary"] if run else card["result"]) or ""
    return cards, done


def open_prs(repo, run=subprocess.run):
    """Open PRs from GitHub, or None when the check fails; a failed check is not an empty list."""
    if not repo:
        return None
    env = dict(os.environ)
    # The gh login lives in the terminal home, not the gateway's HOME.
    if Path("/opt/data/home").is_dir():
        env["HOME"] = "/opt/data/home"
    try:
        result = run(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", str(PR_LIMIT), "--json",
                      "number,title,headRefName,baseRefName,isDraft"], capture_output=True, text=True, timeout=20, env=env)
        return json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _short(text, limit=220):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render(project, extra, cards, done, prs, source, now):
    slug = project["slug"]
    lines = [
        f"[Project status: {project['name']} ({slug}). Read live from Kanban and GitHub at {now:%Y-%m-%d %H:%M} UTC.]",
        f"Source: {source}",
    ]
    if extra.get("repo") or project["primary_path"]:
        lines.append(f"Repo: {extra.get('repo') or 'unknown'} at {project['primary_path'] or 'no folder'}")
    if extra.get("plan"):
        lines.append(f"Plan and goal: read {extra['plan']}")
    lines.append(f"Open cards ({len(cards)}):" if cards else "Open cards: none.")
    for card in cards:
        branch = f", branch {card['branch_name']}" if card["branch_name"] else ""
        lines.append(f"- {card['id']} [{card['status']}, {card['assignee'] or 'unassigned'}{branch}] {_short(card['title'])}")
        if card["reason"]:
            lines.append(f"  blocked: {_short(card['reason'])}")
        if card["note"]:
            lines.append(f"  last note: {_short(card['note'])}")
    if done:
        lines.append(f"Last {len(done)} done cards:")
        for card in done:
            day = datetime.fromtimestamp(card["completed_at"], timezone.utc).strftime("%Y-%m-%d") if card["completed_at"] else "?"
            lines.append(f"- {card['id']} ({day}) {_short(card['title'])}: {_short(card['summary']) or 'no summary'}")
    if prs is None:
        lines.append("Open PRs: the GitHub check failed. Run `gh pr list` before you state PR status.")
    else:
        lines.append(f"Open PRs ({len(prs)}):" if prs else "Open PRs: none.")
        for pr in prs:
            draft = ", draft" if pr.get("isDraft") else ""
            lines.append(f"- #{pr['number']} {_short(pr['title'])} ({pr['headRefName']} -> {pr['baseRefName']}{draft})")
    needs = [f"card {c['id']}" for c in cards if c["status"] == "blocked"]
    needs += [f"PR #{p['number']}" for p in prs or [] if p["baseRefName"] in DEFAULT_BRANCHES and not p.get("isDraft")]
    lines.append("Needs Mitch: " + (", ".join(needs) if needs else "nothing found."))
    lines.append(
        "Use only this block, Kanban and gh for task and PR status. Memory gives history and decisions, never status. "
        f"Later in this chat, run `python3 {Path(__file__).resolve()} {slug}` before you state status again."
    )
    return "\n".join(lines)


def status_text(home, project, source, run=subprocess.run, now=None):
    extra = load_extras(home / "scripts" / "projects.txt").get(project["slug"], {})
    cards, done = load_cards(home, project)
    return render(project, extra, cards, done, open_prs(extra.get("repo"), run), source, now or datetime.now(timezone.utc))


def _message_text(message):
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return " ".join(part.get("text", "") for part in message if isinstance(part, dict))
    return ""


def hook_context(home, payload, run=subprocess.run):
    """The status block for a chat's first turn, or None. Reads only; binds nothing."""
    extra = payload.get("extra") or {}
    if not extra.get("is_first_turn") or extra.get("kanban_task_id"):
        return None
    session = _rows(home / "state.db", "SELECT cwd, source, parent_session_id FROM sessions WHERE id = ?",
                    [payload.get("session_id") or ""])
    row = session[0] if session else {}
    if row.get("parent_session_id") or row.get("source") in SKIP_SOURCES:
        return None
    projects = load_projects(home)
    project = project_for_path(projects, row.get("cwd"))
    if project:
        return status_text(home, project, f"this chat's folder is {row['cwd']}.", run)
    named = projects_named(projects, _message_text(extra.get("user_message")))
    # Two names are ambiguous: inject nothing rather than the wrong project.
    if len(named) != 1:
        return None
    return status_text(home, named[0], "the first message names this project. This chat is not bound to it.", run)


def main(argv):
    home = hermes_home()
    if argv[1:] == ["--hook"]:
        # A hook failure must never block the turn: print nothing and exit 0.
        try:
            context = hook_context(home, json.load(sys.stdin))
            if context:
                print(json.dumps({"context": context}))
        except Exception as exc:  # noqa: BLE001
            print(f"[project-status] hook skipped: {exc}", file=sys.stderr)
        return 0
    if len(argv) != 2:
        print("usage: project-status.py <project-slug> | --hook", file=sys.stderr)
        return 2
    project = next((p for p in load_projects(home) if argv[1] in (p["slug"], p["id"])), None)
    if not project:
        print(f"No registered project '{argv[1]}'. Run `hermes project list`.", file=sys.stderr)
        return 1
    print(status_text(home, project, "requested by command."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
