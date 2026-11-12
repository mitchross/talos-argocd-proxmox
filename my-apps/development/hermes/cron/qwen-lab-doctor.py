#!/usr/bin/env python3
# Puts the qwen-lab Kanban board back in line: reclaims cards whose worker died, starts ready cards, reports the rest.
import json, os, socket, sqlite3, subprocess, time
from pathlib import Path

H = "/opt/hermes/bin/hermes"
ROOT = Path(os.environ.get("QWEN_LAB_ROOT", "/opt/data"))
DB = ROOT / "kanban/boards/qwen-lab/kanban.db"
LOG = ROOT / "workspace/reports/qwen-lab/doctor.log"
SLOTS = 4  # two 3090s: more than 4 busy bots slows every card
GRACE = 120  # seconds a fresh claim is left alone
STALE = 900  # seconds without a heartbeat before a live-looking worker counts as dead
HELPERS = ("qwen-worker", "qwen-reviewer", "qwen-researcher", "qwen-designer")


def ro(path):
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def alive(pid):
    try:
        return b"hermes" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False


def dead_cards(rows, host, now):
    """Running cards whose worker is gone: other pod, missing process, or no heartbeat."""
    out = []
    for r in rows:
        lock_host = (r["claim_lock"] or "").rsplit(":", 1)[0]
        beat = max(r["last_heartbeat_at"] or 0, r["started_at"] or 0)  # worker_started_at is an id string, not a time
        if lock_host and lock_host != host:
            out.append((r["id"], "worker was on a pod that is gone"))
        elif now - beat < GRACE:
            continue  # just claimed: the worker process may not exist yet
        elif not r["worker_pid"] or not alive(r["worker_pid"]):
            out.append((r["id"], "worker process is gone"))
        elif now - beat > STALE:
            out.append((r["id"], f"no heartbeat for {int((now - beat) / 60)} min"))
    return out


def stray_chats(root, now):
    """Helper bots doing real work outside a card: the job belongs to Qwen Lead."""
    out = []
    for name in HELPERS:
        db = root / "profiles" / name / "state.db"
        if not db.exists():
            continue
        with ro(db) as conn:
            q = ("select id, api_call_count from sessions where source in ('desktop','tui') "
                 "and api_call_count >= 10 and id in (select session_id from messages where timestamp > ?)")
            out += [f"{name} chat {r['id']} is doing a big job outside a card ({r['api_call_count']} calls)"
                    for r in conn.execute(q, (now - 600,))]
    return out


def main():
    if not DB.exists():
        return
    now, run = time.time(), lambda *a: subprocess.run([H, "kanban", "--board", "qwen-lab", *a], capture_output=True, text=True, timeout=120)
    with ro(DB) as conn:
        rows = conn.execute("select * from tasks where status in ('running','ready','blocked')").fetchall()
    by = lambda s: [r for r in rows if r["status"] == s]
    out = []
    dead = dead_cards(by("running"), socket.gethostname(), now)
    for card, why in dead:
        r = run("reclaim", card, "--reason", f"lab doctor: {why}")
        out.append(f"reclaimed {card}: {why} ({r.returncode})")
    if dead or (by("ready") and len(by("running")) - len(dead) < SLOTS):
        started = [t["task_id"] for t in json.loads(run("dispatch", "--max", str(SLOTS), "--json").stdout or "{}").get("spawned", [])]
        out += [f"started {t}" for t in started]
    out += [f"BLOCKED {r['id']} {r['title'][:60]}: needs Mitch or the lead" for r in by("blocked")]
    try:
        out += stray_chats(ROOT, now)
    except sqlite3.Error as exc:
        out.append(f"stray-chat check failed: {exc}")
    seen = LOG.read_text()[-4000:] if LOG.exists() else ""
    out = [line for line in out if line.startswith(("reclaimed", "started")) or line not in seen]  # report a standing problem once
    if out:
        stamp = time.strftime("%Y-%m-%d %H:%M")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.writelines(f"{stamp} {line}\n" for line in out)
        print("\n".join(out))


if __name__ == "__main__":
    main()
