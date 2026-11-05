"""Verify startup recovery preserves active work and the upstream PR guard."""

import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

SCRIPT = Path(__file__).resolve().parents[2] / "my-apps/development/hermes/scripts/reconcile-kanban.py"
spec = importlib.util.spec_from_file_location("hermes_kanban_reconcile", SCRIPT)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class KanbanReconciliationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db_path = Path(temp.name) / "kanban.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE tasks (id TEXT, status TEXT, claim_lock TEXT, current_run_id INTEGER);
                CREATE TABLE task_runs (
                    id INTEGER, task_id TEXT, started_at INTEGER,
                    ended_at INTEGER, status TEXT, outcome TEXT
                );
                INSERT INTO tasks VALUES ('crashed', 'ready', NULL, NULL);
                INSERT INTO tasks VALUES ('healthy', 'ready', NULL, NULL);
                INSERT INTO tasks VALUES ('running', 'running', 'claim', 3);
                INSERT INTO tasks VALUES ('blocked', 'blocked', NULL, NULL);
                INSERT INTO task_runs VALUES (1, 'crashed', 1, 2, 'crashed', 'crashed');
                INSERT INTO task_runs VALUES (2, 'healthy', 1, 2, 'done', 'completed');
                INSERT INTO task_runs VALUES (3, 'running', 1, NULL, 'running', NULL);
                INSERT INTO task_runs VALUES (4, 'blocked', 1, 2, 'crashed', 'crashed');
            """)

    def test_only_crashed_ready_guarded_task_uses_supported_block_command(self):
        guard = Mock(return_value="active_pr")
        run = Mock()
        self.assertEqual(recovery.reconcile(self.db_path, guard, run), ["crashed"])
        self.assertEqual(guard.call_count, 1)
        self.assertEqual(guard.call_args.args[1], "crashed")
        self.assertEqual(run.call_args.args[0][:4], ["/opt/hermes/bin/hermes", "kanban", "block", "crashed"])
        self.assertTrue(run.call_args.kwargs["check"])

    def test_expired_pr_guard_or_explicit_handoff_does_not_block(self):
        run = Mock()
        self.assertEqual(recovery.reconcile(self.db_path, Mock(return_value=None), run), [])
        run.assert_not_called()

    def test_new_successful_run_supersedes_old_crash(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO task_runs VALUES (5, 'crashed', 3, 4, 'done', 'completed')")
        run = Mock()
        self.assertEqual(recovery.reconcile(self.db_path, Mock(return_value="active_pr"), run), [])
        run.assert_not_called()

    def test_missing_database_does_not_initialize_runtime_state(self):
        path = self.db_path.parent / "new.db"
        self.assertEqual(recovery.reconcile(path, Mock(), Mock()), [])
        self.assertFalse(path.exists())

    def test_failed_command_is_reported_and_sqlite_reader_cannot_write(self):
        def guard(conn, task_id):
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("UPDATE tasks SET status = 'blocked'")
            return "active_pr"

        run = Mock(side_effect=subprocess.CalledProcessError(1, "hermes"))
        with self.assertRaises(subprocess.CalledProcessError):
            recovery.reconcile(self.db_path, guard, run)
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT status FROM tasks WHERE id = 'crashed'").fetchone()[0], "ready")


if __name__ == "__main__":
    unittest.main()
