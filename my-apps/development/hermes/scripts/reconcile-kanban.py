"""Park crashed, PR-guarded tasks before the gateway starts accepting work."""

from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import site
import sqlite3
import subprocess
import sys


def reconcile(db_path, check_guard, run=subprocess.run):
    if not db_path.exists():
        return []
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        tasks = conn.execute("""
            SELECT t.id FROM tasks t
            JOIN task_runs r ON r.id = (
                SELECT id FROM task_runs WHERE task_id = t.id
                ORDER BY id DESC LIMIT 1
            )
            WHERE t.status = 'ready' AND t.claim_lock IS NULL
              AND t.current_run_id IS NULL AND r.outcome = 'crashed'
              AND r.status = 'crashed' AND r.ended_at IS NOT NULL
        """).fetchall()
        guarded = [row["id"] for row in tasks if check_guard(conn, row["id"]) == "active_pr"]
    recovered = []
    for task_id in guarded:
        run([
            "/opt/hermes/bin/hermes", "kanban", "block", task_id,
            "Worker crashed after linking a PR. Inspect the existing PR and task diagnostics; "
            "use the review workflow or an explicit handoff to continue existing work.",
        ], check=True, timeout=30)
        recovered.append(task_id)
        print(f"[kanban] blocked {task_id}: crashed worker with an active PR guard", flush=True)
    return recovered


def main():
    # The bundled interpreter needs the launcher's source path and .pth dependency paths.
    sys.path.insert(0, "/opt/hermes")
    site.addsitedir("/opt/hermes/.venv/lib/python3.14/site-packages")
    try:
        from hermes_cli.kanban_db_dispatch import check_respawn_guard

        reconcile(Path(os.environ.get("HERMES_HOME", "/opt/data")) / "kanban.db", check_respawn_guard)
    except (ImportError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(f"[kanban] reconciliation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
