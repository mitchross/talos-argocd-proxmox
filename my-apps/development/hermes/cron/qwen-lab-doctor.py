#!/usr/bin/env python3
# Puts the qwen-lab and default Kanban boards back in line: reclaims dead cards and reports blocks. --dry-run changes nothing.
import json, os, socket, sqlite3, subprocess, sys, time
from pathlib import Path

H = "/opt/hermes/bin/hermes"
ROOT = Path(os.environ.get("QWEN_LAB_ROOT", "/opt/data"))
DB = ROOT / "kanban/boards/qwen-lab/kanban.db"
DEFAULT_DB = ROOT / "kanban.db"
LAB = ROOT / "workspace/qwen-lab"
LOG = ROOT / "workspace/reports/qwen-lab/doctor.log"
STATE = LOG.with_name("doctor-state.json")
SLOTS = 4  # two 3090s: more than 4 busy bots slows every card
GRACE = 120  # seconds a fresh claim is left alone
STALE = 900  # seconds without a heartbeat before a live-looking worker counts as dead
KEEP = 7 * 86400  # a finding gone this long pings again if it comes back
DAILY = 86400  # default-board blocked cards re-ping at most once a day while still blocked
SLACK = 120  # seconds of clock slack when matching a move of main to a card run
HELPERS = ("qwen-worker", "qwen-reviewer", "qwen-researcher", "qwen-designer")
LEAD, REVIEWER, SPEC = "qwen-lab", "qwen-reviewer", "docs/SPEC.md"


def ro(path):
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    return r.stdout if r.returncode == 0 else ""


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
            out += [(f"chat:{name}:{r['id']}", f"{name} chat {r['id']} is doing a big job outside a card ({r['api_call_count']} calls)")
                    for r in conn.execute(q, (now - 600,))]
    return out


def blocked_cards(conn):
    """(card, title, id of the block event, reason) for every blocked card a worker or the board blocked."""
    q = ("select t.id, t.title, t.last_failure_error err, e.id ev, e.kind, e.payload from tasks t left join task_events e on e.id = "
         "(select max(id) from task_events where task_id = t.id and kind in ('blocked','gave_up')) where t.status = 'blocked'")
    out = []
    for r in conn.execute(q):
        try:
            p = json.loads(r["payload"] or "{}")
        except ValueError:
            p = {}
        if p.get("reason") == "initial_status":
            continue  # created blocked on purpose: a parked card, not a stuck one
        reason = p.get("reason") or (r["kind"] == "gave_up" and f"gave up after {p.get('failures')} failures: {r['err'] or p.get('error')}") or r["err"]
        out.append((r["id"], r["title"], r["ev"] or 0, " ".join(str(reason or "no reason given").split())))
    return out


def parent_problems(conn):
    """Links whose parent card is gone, or that were added after the child had started."""
    tasks = {r["id"]: r for r in conn.execute("select id, status, created_at from tasks")}
    first = dict(conn.execute("select task_id, min(started_at) from task_runs group by task_id").fetchall())
    linked = {}
    for r in conn.execute("select task_id, payload, created_at from task_events where kind = 'linked'"):
        try:
            linked[(json.loads(r["payload"])["parent"], r["task_id"])] = r["created_at"]
        except (ValueError, KeyError, TypeError):
            pass
    out = []
    for parent, child in conn.execute("select parent_id, child_id from task_links").fetchall():
        if child not in tasks or tasks[child]["status"] == "archived":
            continue
        if parent not in tasks:
            out.append((f"parent:{child}:{parent}", f"{child} waits on parent {parent}, which is not on the board"))
            continue
        added = linked.get((parent, child), tasks[parent]["created_at"])  # old links have no event: the parent is at least this new
        if child in first and added > first[child]:
            mins = int((added - first[child]) / 60)
            out.append((f"late:{child}:{parent}", f"{child} got parent {parent} {mins} min after it started"))
    return out


def repo_of(path):
    path = (path or "").split("/.worktrees/")[0]
    return Path(path).resolve() if path and (Path(path) / ".git").is_dir() else None


def bad_main_moves(repo, cards, runs, links, now):
    """Moves of main (from its reflog) that did not come from a lead merge card after a passed review."""
    lead = [(c["id"], s, e) for c in cards if c["assignee"] == LEAD and repo_of(c["workspace_path"]) == repo
            for s, e in runs.get(c["id"], [])]
    by_id = {c["id"]: c for c in cards}
    out = []
    for line in git(repo, "reflog", "show", "--date=unix", "--format=%H %gd %gs", "main").splitlines():
        sha, sel, msg = (line.split(" ", 2) + ["", ""])[:3]
        t, kind = int(sel.split("@{")[-1].rstrip("}") or 0), msg.split(":", 1)[0]
        why = None
        if kind.startswith("commit"):
            files = set(git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha).split())
            has_parent = len(git(repo, "rev-list", "--parents", "-n1", sha).split()) > 1
            if has_parent and not files <= {SPEC}:  # the repo's first commit and the lead's spec commits are expected
                why = f"commit straight on main ({msg.split(': ', 1)[-1][:60]})"
        elif kind.startswith("merge"):
            card = next((c for c, s, e in lead if s - SLACK <= t <= (e or now) + SLACK), None)
            reviews = [by_id[p] for p in links.get(card, []) if p in by_id and by_id[p]["assignee"] == REVIEWER]
            if not card:
                why = f"{msg[:60]} outside a lead merge card"
            elif not any(r["status"] in ("done", "archived") and (r["completed_at"] or now + 1) <= t + SLACK for r in reviews):
                why = f"{msg[:60]} by {card} before a review passed"
        else:
            why = f"main moved by '{msg[:60]}'"
        if why:
            out.append((f"main:{repo}:{sha}:{t}", f"{repo.name} main {sha[:7]}: {why}"))
    return out


def strays(repo, cards):
    """Worktrees and branches in a repo that no card owns. Report only, never delete."""
    ids = {c["id"] for c in cards}
    paths = {c["workspace_path"] for c in cards if c["workspace_path"]}
    branches = {c["branch_name"] for c in cards if c["branch_name"]} | {f"wt/{i}" for i in ids}
    wts, cur = [], {}
    for line in git(repo, "worktree", "list", "--porcelain").splitlines() + [""]:
        if line:
            k, _, v = line.partition(" ")
            cur[k] = v
        elif cur:
            wts, cur = wts + [cur], {}
    loose = [w["worktree"] for w in wts[1:] if w["worktree"] not in paths and Path(w["worktree"]).name not in ids
             and w.get("branch", "").removeprefix("refs/heads/") not in branches]
    loose += [b for b in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
              if b not in ("main", "master") and b not in branches]
    if not loose:
        return []
    names = sorted(Path(x).name if x.startswith("/") else x for x in loose)
    return [(f"stray:{repo}:{','.join(names)}",
             f"{repo.name}: {len(names)} worktrees/branches no card owns, left in place: {', '.join(names)[:200]}")]


def check_board(conn, now, lab):
    """Read-only findings for one board as (dedupe key, line)."""
    cards = [dict(r) for r in conn.execute("select * from tasks")]
    runs, links = {}, {}
    for r in conn.execute("select task_id, started_at, ended_at from task_runs"):
        runs.setdefault(r["task_id"], []).append((r["started_at"], r["ended_at"]))
    for parent, child in conn.execute("select parent_id, child_id from task_links").fetchall():
        links.setdefault(child, []).append(parent)
    out = [(f"block:{c}:{ev}", f"BLOCKED {c} {title[:60]}: {why[:160]}") for c, title, ev, why in blocked_cards(conn)]
    out += parent_problems(conn)
    if not lab:
        return out  # default-board cards span many GitHub repos where PRs, not cards, gate main
    repos = {r for c in cards if (r := repo_of(c["workspace_path"]))}
    repos |= {p.resolve() for p in LAB.iterdir() if (p / ".git").is_dir()} if LAB.is_dir() else set()
    for repo in sorted(repos):
        out += bad_main_moves(repo, cards, runs, links, now) + strays(repo, cards)
    return out


def fresh(findings, state, now):
    """Findings due to report; default-board blocks re-ping at most once a day, others remember for KEEP."""
    seen = state.setdefault("seen", {})
    present = {k for k, _ in findings}
    new = []
    for k, line in findings:
        if k.startswith("default:block:"):
            if k not in seen or now - seen[k] >= DAILY:
                new.append((k, line))
                seen[k] = now
        else:
            if k not in seen:
                new.append((k, line))
            seen[k] = now
    for k in [k for k, t in seen.items() if (k.startswith("default:block:") and k not in present) or now - t > KEEP]:
        del seen[k]
    return new


def checks(db, label, now, lab):
    """A board's findings with keys and lines tagged by board; a failing check is itself a finding."""
    try:
        with ro(db) as conn:
            found = check_board(conn, now, lab)
    except (sqlite3.Error, OSError, subprocess.SubprocessError) as exc:
        found = [("check-failed", f"checks failed: {exc}")]
    prefix = "" if lab else f"{label} board: "
    return [(f"{label}:{k}", prefix + line) for k, line in found]


def main(dry=False):
    now = time.time()
    run = lambda *a: subprocess.run([H, "kanban", "--board", "qwen-lab", *a], capture_output=True, text=True, timeout=120)
    run_default = lambda *a: subprocess.run([H, "kanban", *a], capture_output=True, text=True, timeout=120)
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {}
    acts, found = [], []
    if DB.exists():
        with ro(DB) as conn:
            rows = conn.execute("select * from tasks where status in ('running','ready')").fetchall()
        by = lambda s: [r for r in rows if r["status"] == s]
        dead = dead_cards(by("running"), socket.gethostname(), now)
        for card, why in dead:
            rc = "dry-run" if dry else run("reclaim", card, "--reason", f"lab doctor: {why}").returncode
            acts.append(f"reclaimed {card}: {why} ({rc})")
        if not dry and (dead or (by("ready") and len(by("running")) - len(dead) < SLOTS)):
            started = [t["task_id"] for t in json.loads(run("dispatch", "--max", str(SLOTS), "--json").stdout or "{}").get("spawned", [])]
            acts += [f"started {t}" for t in started]
        found += checks(DB, "qwen-lab", now, lab=True)
        try:
            found += stray_chats(ROOT, now)
        except sqlite3.Error as exc:
            found.append(("chat-check", f"stray-chat check failed: {exc}"))
    if DEFAULT_DB.exists():
        with ro(DEFAULT_DB) as conn:
            running = conn.execute("select * from tasks where status = 'running'").fetchall()
        for card, why in dead_cards(running, socket.gethostname(), now):
            rc = "dry-run" if dry else run_default("reclaim", card, "--reason", f"lab doctor: {why}").returncode
            acts.append(f"default board: reclaimed {card}: {why} ({rc})")
        found += checks(DEFAULT_DB, "default", now, lab=False)
    if dry:
        new = {k for k, _ in fresh(found, json.loads(json.dumps(state)), now)}
        print("\n".join(acts + [f"{'NEW ' if k in new else 'seen'} {line}" for k, line in found]) or "nothing to report")
        return
    new = fresh(found, state, now)
    for key, line in new:
        if key.startswith("qwen-lab:block:"):  # tell the lead on the blocked card itself
            card = key.split(":")[2]
            body = f"Lab doctor: this card is blocked. Reason: {line.split(': ', 1)[-1]} Lead: unblock it, re-plan it, or ask Mitch."
            acts.append(f"commented on {card} ({run('comment', card, body, '--author', 'qwen-lab-doctor').returncode})")
    out = acts + [line for _, line in new]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))
    if out:  # printed output is the ping: a script cron run that prints something reaches Mitch
        stamp = time.strftime("%Y-%m-%d %H:%M")
        with LOG.open("a") as f:
            f.writelines(f"{stamp} {line}\n" for line in out)
        print("\n".join(out))


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
