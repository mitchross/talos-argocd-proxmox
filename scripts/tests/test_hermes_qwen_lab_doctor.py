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
