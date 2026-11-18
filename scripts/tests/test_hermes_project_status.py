"""Verify the project status hook binds a chat to the right project and reads only live state."""

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

SCRIPT = Path(__file__).resolve().parents[2] / "my-apps/development/hermes/scripts/project-status.py"
spec = importlib.util.spec_from_file_location("hermes_project_status", SCRIPT)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)

RADAR = "/opt/data/workspace/radar-ng"
PRS = [
    {"number": 341, "title": "snow notice", "headRefName": "feat/snow", "baseRefName": "feat/weather-extras", "isDraft": False},
    {"number": 350, "title": "weather extras", "headRefName": "feat/weather-extras", "baseRefName": "master", "isDraft": False},
]


def gh(prs=PRS, returncode=0):
    return Mock(return_value=Mock(returncode=returncode, stdout=json.dumps(prs)))


class ProjectStatusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        (self.home / "scripts").mkdir()
        (self.home / "scripts/projects.txt").write_text(
            "# comment\nradar-ng|Radar NG|/opt/data/workspace/radar-ng|mitchross/radar-ng|/plans/radar.md\n"
        )
        with sqlite3.connect(self.home / "projects.db") as conn:
            conn.executescript(f"""
                CREATE TABLE projects (id TEXT, slug TEXT, name TEXT, board_slug TEXT, primary_path TEXT, archived INTEGER);
                CREATE TABLE project_folders (project_id TEXT, path TEXT);
                INSERT INTO projects VALUES ('p_radar', 'radar-ng', 'Radar NG', NULL, '{RADAR}', 0);
                INSERT INTO projects VALUES ('p_deal', 'deal-scout', 'Deal Scout', NULL, '/opt/data/workspace/deal-scout', 0);
                INSERT INTO projects VALUES ('p_old', 'old-app', 'Old App', NULL, '/opt/data/workspace/old', 1);
                INSERT INTO project_folders VALUES ('p_radar', '{RADAR}');
            """)
        with sqlite3.connect(self.home / "kanban.db") as conn:
            conn.executescript("""
                CREATE TABLE tasks (id TEXT, title TEXT, status TEXT, assignee TEXT, branch_name TEXT, project_id TEXT,
                                    created_at INTEGER, completed_at INTEGER, result TEXT);
                CREATE TABLE task_events (id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT);
                CREATE TABLE task_comments (id INTEGER PRIMARY KEY, task_id TEXT, author TEXT, body TEXT);
                CREATE TABLE task_runs (id INTEGER PRIMARY KEY, task_id TEXT, summary TEXT);
                INSERT INTO tasks VALUES ('t_run', 'radar-ng #320 snow-chance: build', 'running', 'default', NULL, NULL, 1, NULL, NULL);
                INSERT INTO tasks VALUES ('t_blk', 'radar-ng #306 review', 'blocked', 'default', NULL, NULL, 2, NULL, NULL);
                INSERT INTO tasks VALUES ('t_link', 'storm sweep polish', 'todo', NULL, 'radar-ng/t_link', 'p_radar', 3, NULL, NULL);
                INSERT INTO tasks VALUES ('t_done', 'radar-ng #322 snow-notice', 'done', 'default', NULL, NULL, 4, 1794960000, NULL);
                INSERT INTO tasks VALUES ('t_deal', 'deal-scout #168: rebase', 'blocked', 'default', NULL, NULL, 5, NULL, NULL);
                INSERT INTO task_events (task_id, kind, payload) VALUES ('t_blk', 'blocked', '{"reason": "PR 306 green, ready for review"}');
                INSERT INTO task_events (task_id, kind, payload) VALUES ('t_deal', 'blocked', '{"reason": "deal secret reason"}');
                INSERT INTO task_comments (task_id, author, body) VALUES ('t_run', 'default', 'Next: wire the legend');
                INSERT INTO task_runs (task_id, summary) VALUES ('t_done', 'Built #322 in PR 341');
            """)
        with sqlite3.connect(self.home / "state.db") as conn:
            conn.executescript(f"""
                CREATE TABLE sessions (id TEXT, cwd TEXT, source TEXT, parent_session_id TEXT);
                INSERT INTO sessions VALUES ('bound', '{RADAR}/apps/web', 'desktop', NULL);
                INSERT INTO sessions VALUES ('unbound', NULL, 'desktop', NULL);
                INSERT INTO sessions VALUES ('worker', '{RADAR}', 'kanban', NULL);
                INSERT INTO sessions VALUES ('child', '{RADAR}', 'desktop', 'bound');
            """)

    def payload(self, session, message="hello", first=True, **extra):
        return {"session_id": session, "cwd": "/opt/data", "extra": {"is_first_turn": first, "user_message": message, **extra}}

    def context(self, *args, run=None, **kwargs):
        return status.hook_context(self.home, self.payload(*args, **kwargs), run or gh())

    def test_bound_session_gets_only_its_project(self):
        text = self.context("bound")
        self.assertIn("Project status: Radar NG (radar-ng)", text)
        self.assertIn(f"this chat's folder is {RADAR}/apps/web", text)
        for expected in ("t_run [running, default]", "last note: default: Next: wire the legend",
                         "blocked: PR 306 green", "t_link [todo, unassigned, branch radar-ng/t_link]",
                         "t_done (2026-11-18) radar-ng #322 snow-notice: Built #322 in PR 341",
                         "#341 snow notice (feat/snow -> feat/weather-extras)", "read /plans/radar.md"):
            self.assertIn(expected, text)
        self.assertIn("Needs Mitch: card t_blk, PR #350", text)
        self.assertNotIn("deal", text)

    def test_unbound_session_without_a_project_name_gets_nothing(self):
        self.assertIsNone(self.context("unbound", "fix the Longhorn alert"))
        self.assertIsNone(self.context("unknown-session", "fix the Longhorn alert"))

    def test_first_message_naming_one_project_gets_an_unbound_snapshot(self):
        for message in ("Where did we leave off with Radar NG?", "status of radar-ng", [{"type": "text", "text": "radarng?"}]):
            text = self.context("unbound", message)
            self.assertIn("This chat is not bound to it", text)
            self.assertIn("t_run", text)

    def test_ambiguous_or_partial_names_get_nothing(self):
        self.assertIsNone(self.context("unbound", "compare Radar NG with deal-scout"))
        self.assertIsNone(self.context("unbound", "the radar-ngx fork"))
        self.assertIsNone(self.context("unbound", "restore Old App"))

    def test_later_turns_workers_and_subagents_get_nothing(self):
        self.assertIsNone(self.context("bound", first=False))
        self.assertIsNone(self.context("bound", kanban_task_id="t_run"))
        self.assertIsNone(self.context("worker"))
        self.assertIsNone(self.context("child"))

    def test_a_failed_github_check_is_not_reported_as_no_prs(self):
        text = self.context("bound", run=gh(returncode=1))
        self.assertIn("the GitHub check failed", text)
        self.assertNotIn("Open PRs: none", text)
        self.assertIn("Open PRs: none.", self.context("bound", run=gh(prs=[])))

    def test_the_hook_binds_nothing_and_writes_nothing(self):
        before = {p.name: p.read_bytes() for p in self.home.glob("*.db")}
        self.context("unbound", "Where did we leave off with Radar NG?")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.home.glob("*.db")})
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["kanban.db", "projects.db", "scripts", "state.db"])

    def test_status_survives_a_new_process(self):
        # A fresh process has no memory: the block must come from the files alone, over the real hook wire.
        env = {**os.environ, "HERMES_HOME": str(self.home), "PATH": "/nonexistent"}
        result = subprocess.run([sys.executable, str(SCRIPT), "--hook"], input=json.dumps(self.payload("bound")),
                                capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0)
        context = json.loads(result.stdout)["context"]
        self.assertIn("t_run [running, default]", context)
        self.assertIn("the GitHub check failed", context)

    def test_a_broken_hook_never_blocks_the_turn(self):
        env = {**os.environ, "HERMES_HOME": str(self.home)}
        result = subprocess.run([sys.executable, str(SCRIPT), "--hook"], input="not json", capture_output=True,
                                text=True, env=env, timeout=30)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_longest_folder_wins_and_bound_board_reads_its_own_database(self):
        projects = status.load_projects(self.home)
        projects.append({"id": "p_web", "slug": "radar-web", "name": "Radar Web", "board_slug": "radar-web",
                         "primary_path": f"{RADAR}/apps/web", "folders": [f"{RADAR}/apps/web"]})
        self.assertEqual(status.project_for_path(projects, f"{RADAR}/apps/web/src")["slug"], "radar-web")
        self.assertEqual(status.project_for_path(projects, f"{RADAR}-old"), None)
        self.assertEqual(status.board_db(self.home, "radar-web"), self.home / "kanban/boards/radar-web/kanban.db")
        self.assertEqual(status.load_cards(self.home, projects[-1]), ([], []))

    def test_command_mode_prints_the_named_project(self):
        project = status.load_projects(self.home)[0]
        text = status.status_text(self.home, project, "requested by command.", gh(), datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc))
        self.assertTrue(text.startswith("[Project status: Radar NG (radar-ng). Read live from Kanban and GitHub at 2026-11-18 03:00 UTC.]"))


if __name__ == "__main__":
    unittest.main()
