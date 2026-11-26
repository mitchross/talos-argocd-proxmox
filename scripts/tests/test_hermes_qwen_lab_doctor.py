"""Guard the Qwen Lab doctor: it reclaims only cards whose worker is really gone."""
import importlib.util
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parents[2] / 'my-apps/development/hermes'
spec = importlib.util.spec_from_file_location('qwen_lab_doctor', APP / 'cron/qwen-lab-doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def _card(card, lock, pid, beat):
    return {'id': card, 'claim_lock': lock, 'worker_pid': pid, 'last_heartbeat_at': beat,
            'worker_started_at': '3066defb-8d55:4492960|4751281', 'started_at': beat}


def test_dead_cards_finds_old_pod_missing_process_and_stale_heartbeat(monkeypatch):
    monkeypatch.setattr(doctor, 'alive', lambda pid: pid == 100)
    now = 10_000
    rows = [
        _card('healthy', 'pod-b:1', 100, now - 300),
        _card('old-pod', 'pod-a:1', 100, now - 5),
        _card('no-process', 'pod-b:1', 999, now - 300),
        _card('just-claimed', 'pod-b:1', None, now - 5),
        _card('silent', 'pod-b:1', 100, now - doctor.STALE - 1),
    ]
    assert [card for card, _ in doctor.dead_cards(rows, 'pod-b', now)] == ['old-pod', 'no-process', 'silent']


def test_doctor_is_a_git_cron_job():
    jobs = (APP / 'cron/jobs.txt').read_text()
    assert 'qwen-lab-doctor|every 5m|qwen-lab-doctor.py|' in jobs
    files = yaml.safe_load((APP / 'kustomization.yaml').read_text())['configMapGenerator']
    assert any('cron-qwen-lab-doctor.py=cron/qwen-lab-doctor.py' in g.get('files', []) for g in files)


def test_helpers_think_less_and_workers_have_no_subagents():
    profiles = yaml.safe_load((APP / 'qwen-lab/profiles.yaml').read_text())
    for name in ('qwen-worker', 'qwen-researcher', 'qwen-designer'):
        assert profiles[name]['config']['agent']['reasoning_effort'] == 'medium', name
    assert 'delegation' in profiles['qwen-worker']['config']['agent']['disabled_toolsets']
    base_off = yaml.safe_load((APP / 'qwen-lab/base.yaml').read_text())['agent']['disabled_toolsets']
    assert set(base_off) <= set(profiles['qwen-worker']['config']['agent']['disabled_toolsets'])


def test_lab_reads_each_image_in_its_own_call():
    vision = yaml.safe_load((APP / 'qwen-lab/base.yaml').read_text())['auxiliary']['vision']
    assert (vision['provider'], vision['model']) == ('homelab-vllm', 'qwen3.8-27b')


def test_seed_rewrites_cron_scripts_from_git_on_every_start():
    seed = (APP / 'scripts/seed.sh').read_text()
    loop = seed.split('for src in /etc/hermes-scripts/cron-*.py; do')[1].split('done')[0]
    assert 'install -o 10000' in loop and '[ -e' not in loop


def test_lab_never_waits_on_an_approval_prompt_but_keeps_its_deny_list():
    approvals = yaml.safe_load((APP / 'qwen-lab/base.yaml').read_text())['approvals']
    assert approvals['mode'] == 'off'
    assert {'kubectl *', 'talosctl *', 'omnictl *', 'helm *', 'gh pr merge*', 'claude *', 'codex *'} <= set(approvals['deny'])
    assert 'git push*' not in approvals['deny']


def test_lab_pushes_feature_branches_but_never_main_force_or_delete():
    import fnmatch
    deny = [p.lower() for p in yaml.safe_load((APP / 'qwen-lab/base.yaml').read_text())['approvals']['deny']]
    blocked = lambda cmd: any(fnmatch.fnmatchcase(cmd.lower(), p) for p in deny)
    for ok in ('git push -u gitea license-sweep', 'git push -u origin feat/x', 'git -c credential.helper= push gitea fix-1'):
        assert not blocked(ok), ok
    for bad in ('git push origin main', 'git push gitea HEAD:master', 'git -C /x push origin main',
                'git push --force origin feat/x', 'git push -f origin feat/x', 'git push origin +feat/x',
                'git push --force-with-lease', 'git push origin --delete feat/x', 'git push -d origin feat/x',
                'git push --mirror', 'git push --all'):
        assert blocked(bad), bad


def _board(tmp_path):
    import sqlite3
    conn = sqlite3.connect(tmp_path / 'kanban.db')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        create table tasks (id text primary key, title text, status text, assignee text, workspace_path text,
                            branch_name text, created_at int, started_at int, completed_at int, last_failure_error text);
        create table task_links (parent_id text, child_id text);
        create table task_events (id integer primary key autoincrement, task_id text, kind text, payload text, created_at int);
        create table task_runs (id integer primary key autoincrement, task_id text, started_at int, ended_at int);
    ''')
    return conn


def _git(repo, *args):
    import subprocess
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', *args], check=True, capture_output=True)


def test_blocked_cards_give_the_latest_reason_and_skip_parked_ones(tmp_path):
    conn = _board(tmp_path)
    conn.executemany('insert into tasks (id, title, status, last_failure_error) values (?, ?, ?, ?)',
                     [('stuck', 'Stuck', 'blocked', None), ('parked', 'Parked', 'blocked', None),
                      ('broke', 'Broke', 'blocked', 'pid 1 exited'), ('fine', 'Fine', 'ready', None)])
    conn.executemany('insert into task_events (task_id, kind, payload) values (?, ?, ?)', [
        ('stuck', 'blocked', '{"reason": "old"}'), ('stuck', 'blocked', '{"reason": "needs   a token"}'),
        ('parked', 'blocked', '{"reason": "initial_status"}'), ('broke', 'gave_up', '{"failures": 2}')])
    got = {c: (ev, why) for c, _, ev, why in doctor.blocked_cards(conn)}
    assert got == {'stuck': (2, 'needs a token'), 'broke': (4, 'gave up after 2 failures: pid 1 exited')}


def test_parent_problems_find_missing_and_late_parents(tmp_path):
    conn = _board(tmp_path)
    conn.executemany('insert into tasks (id, status, created_at) values (?, ?, ?)',
                     [('child', 'running', 0), ('ok-parent', 'done', 0), ('late-parent', 'done', 0), ('old', 'archived', 0)])
    conn.executemany('insert into task_links values (?, ?)',
                     [('ok-parent', 'child'), ('late-parent', 'child'), ('gone', 'child'), ('gone', 'old')])
    conn.execute("insert into task_runs (task_id, started_at) values ('child', 100)")
    conn.executemany('insert into task_events (task_id, kind, payload, created_at) values (?, ?, ?, ?)', [
        ('child', 'linked', '{"parent": "ok-parent", "child": "child"}', 50),
        ('child', 'linked', '{"parent": "late-parent", "child": "child"}', 700)])
    assert sorted(k for k, _ in doctor.parent_problems(conn)) == ['late:child:late-parent', 'parent:child:gone']


def test_main_moves_flag_direct_commits_and_unreviewed_merges(tmp_path):
    import time
    repo = tmp_path / 'app'
    _git(tmp_path, 'init', '-q', '-b', 'main', str(repo))
    (repo / 'docs').mkdir()
    (repo / 'docs/SPEC.md').write_text('v1')
    _git(repo, 'add', '.'); _git(repo, 'commit', '-qm', 'start')
    (repo / 'docs/SPEC.md').write_text('v2')
    _git(repo, 'commit', '-qam', 'spec')
    _git(repo, 'switch', '-qc', 'wt/build'); (repo / 'a.js').write_text('1')
    _git(repo, 'add', '.'); _git(repo, 'commit', '-qm', 'build')
    _git(repo, 'switch', '-q', 'main'); _git(repo, 'merge', '-q', 'wt/build')
    (repo / 'b.js').write_text('2')
    _git(repo, 'add', '.'); _git(repo, 'commit', '-qm', 'sneaky')
    now, path = time.time(), str(repo)
    review = {'id': 'review', 'assignee': 'qwen-reviewer', 'status': 'done', 'completed_at': now - 60, 'workspace_path': path}
    merge = {'id': 'merge', 'assignee': 'qwen-lab', 'status': 'done', 'completed_at': now, 'workspace_path': path}
    runs, links = {'merge': [(now - 30, None)]}, {'merge': ['review']}
    lines = [line for _, line in doctor.bad_main_moves(repo, [review, merge], runs, links, now)]
    assert len(lines) == 1 and 'commit straight on main (sneaky)' in lines[0]
    review['status'], review['completed_at'] = 'blocked', None
    lines = [line for _, line in doctor.bad_main_moves(repo, [review, merge], runs, links, now)]
    assert any('by merge before a review passed' in line for line in lines)
    lines = [line for _, line in doctor.bad_main_moves(repo, [review, merge], {}, links, now)]
    assert any('outside a lead merge card' in line for line in lines)


def test_strays_report_unowned_worktrees_and_branches_only(tmp_path):
    repo = tmp_path / 'app'
    _git(tmp_path, 'init', '-q', '-b', 'main', str(repo))
    (repo / 'x').write_text('x')
    _git(repo, 'add', '.'); _git(repo, 'commit', '-qm', 'start')
    _git(repo, 'worktree', 'add', '-q', '-b', 'wt/owned', str(repo / '.worktrees/t_1'))
    _git(repo, 'worktree', 'add', '-q', '-b', 'side', str(tmp_path / 'loose'))
    _git(repo, 'branch', 'old-idea')
    cards = [{'id': 't_1', 'workspace_path': str(repo / '.worktrees/t_1'), 'branch_name': 'wt/owned'}]
    [(_, line)] = doctor.strays(repo, cards)
    assert line.endswith('loose, old-idea, side')
    assert (tmp_path / 'loose').is_dir()


def test_fresh_reports_a_finding_once_and_again_after_it_was_gone_a_week():
    state, day = {}, 86400
    assert doctor.fresh([('a', 'A'), ('b', 'B')], state, 0) == [('a', 'A'), ('b', 'B')]
    assert doctor.fresh([('a', 'A')], state, 300) == []
    assert doctor.fresh([('a', 'A')], state, 8 * day) == []
    assert doctor.fresh([('b', 'B')], state, 8 * day + 1) == [('b', 'B')]
