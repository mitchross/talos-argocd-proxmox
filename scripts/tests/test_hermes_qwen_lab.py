"""Guard Qwen Lab: local-only model routing, a complete team, and a seed that never writes the default profile."""
import os
import sys
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'my-apps/development/hermes'
LAB = APP / 'qwen-lab'
VLLM = 'http://vllm-service.vllm.svc.cluster.local:8080/v1'
TEAM = {'qwen-lab', 'qwen-worker', 'qwen-reviewer', 'qwen-researcher', 'qwen-designer'}


def _base():
    return yaml.safe_load((LAB / 'base.yaml').read_text())


def _profiles():
    return yaml.safe_load((LAB / 'profiles.yaml').read_text())


def test_every_model_route_is_local_vllm():
    base = _base()
    assert base['model'] == {'provider': 'homelab-vllm', 'default': 'qwen3.8-27b'}
    assert list(base['providers']) == ['homelab-vllm']
    assert base['providers']['homelab-vllm']['base_url'] == VLLM
    assert base['fallback_providers'] == []
    assert base['delegation']['provider'] == 'homelab-vllm'
    # Hermes defaults aux tasks to "auto", which falls back to cloud providers; pin every one.
    for task, cfg in base['auxiliary'].items():
        assert cfg['provider'] == 'homelab-vllm', task
        assert cfg['model'] == 'qwen3.8-27b', task
    for task in ('compression', 'approval', 'mcp', 'title_generation', 'curator', 'kanban_decomposer'):
        assert task in base['auxiliary'], task


def test_no_cloud_endpoints_or_keys_in_lab_files():
    # Comments may name what the lab avoids; check config values and the prompt files only.
    text = yaml.safe_dump(_base()) + yaml.safe_dump(_profiles()) + (LAB / 'SOUL.md').read_text()
    text += ''.join(p.read_text() for p in (LAB / 'skills').glob('*.md'))
    for bad in ('litellm', 'openrouter', 'anthropic.com', 'openai.com', 'deepseek.com', 'api.cloudflare'):
        assert bad not in text.lower(), bad
    urls = [w for w in text.split() if w.startswith('http')]
    assert all('.svc' in u for u in urls), urls


def test_team_is_complete_and_skills_exist():
    profiles = _profiles()
    assert set(profiles) == TEAM
    skill_files = {p.stem for p in (LAB / 'skills').glob('*.md')}
    for name, spec in profiles.items():
        assert {'title', 'color', 'description', 'role', 'skills'} <= set(spec), name
        assert set(spec['skills']) <= skill_files, name
    for stem in skill_files:
        front = yaml.safe_load((LAB / 'skills' / f'{stem}.md').read_text().split('---')[1])
        assert front['name'] == stem
        assert len(front['description']) <= 80


def test_configmap_ships_every_lab_file():
    docs = list(yaml.safe_load_all(subprocess.check_output(['kubectl', 'kustomize', str(APP)], text=True)))
    cm = next(d for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'].startswith('hermes-qwen-lab'))
    want = {'base.yaml', 'profiles.yaml', 'SOUL.md'} | {f'skill-{p.name}' for p in (LAB / 'skills').glob('*.md')}
    assert set(cm['data']) == want
    scripts = next(d for d in docs if d['kind'] == 'ConfigMap' and 'seed.sh' in d.get('data', {}))
    assert 'seed-qwen-lab.py' in scripts['data']
    assert 'seed-qwen-lab.py' in scripts['data']['seed.sh']
    deployment = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'hermes')
    mounts = {m['mountPath'] for c in deployment['spec']['template']['spec']['initContainers']
              for m in c.get('volumeMounts', [])}
    assert '/etc/hermes-qwen-lab' in mounts


def test_seed_never_writes_the_default_profile(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    for f in ('base.yaml', 'profiles.yaml', 'SOUL.md'):
        (src / f).write_text((LAB / f).read_text())
    for p in (LAB / 'skills').glob('*.md'):
        (src / f'skill-{p.name}').write_text(p.read_text())
    root = tmp_path / 'root'
    fake = tmp_path / 'hermes'
    # Stand-in CLI: "profile create" makes the dir; every other call is a no-op.
    fake.write_text('#!/bin/sh\nif [ "$1" = profile ] && [ "$2" = create ]; then mkdir -p "$HERMES_HOME/profiles/$3"; fi\n')
    fake.chmod(0o755)
    env = {**os.environ, 'HERMES_HOME': str(root), 'HERMES_BIN': str(fake), 'QWEN_LAB_SRC': str(src),
           'QWEN_LAB_WORKSPACE': str(tmp_path / 'ws')}
    out = subprocess.run([sys.executable, str(APP / 'scripts/seed-qwen-lab.py')], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    top = {p.name for p in root.iterdir()}
    assert top == {'profiles'}, top
    assert {p.name for p in (root / 'profiles').iterdir()} == TEAM
    soul = (root / 'profiles/qwen-reviewer/SOUL.md').read_text()
    assert '{role}' not in soul and 'fresh eyes' in soul
    cfg = yaml.safe_load((root / 'profiles/qwen-worker/config.yaml').read_text())
    assert cfg['model']['provider'] == 'homelab-vllm'
    assert (root / 'profiles/qwen-lab/skills/qwen-lab/qwen-best-of-n/SKILL.md').exists()
    assert not (root / 'profiles/qwen-worker/skills/qwen-lab/qwen-best-of-n').exists()
    meta = yaml.safe_load((root / 'profiles/qwen-lab/profile.yaml').read_text())
    assert meta['ui_meta']['hermes-bots']['sectionName'] == 'Qwen Lab'
    lab_env = (root / 'profiles/qwen-researcher/.env').read_text()
    assert 'SEARXNG_URL=' in lab_env and 'KEY' not in lab_env and 'TOKEN' not in lab_env


def test_default_profile_keeps_pod_secrets_under_multiplex(tmp_path):
    # A second profile turns on multiplexing; then default turns see only .env plus secret sources.
    cfg = yaml.safe_load((APP / 'config/config.yaml').read_text())
    helper = cfg['secrets']['command']['command']
    assert cfg['secrets']['command']['enabled'] is True
    docs = list(yaml.safe_load_all(subprocess.check_output(['kubectl', 'kustomize', str(APP)], text=True)))
    pod = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'hermes')['spec']['template']['spec']
    vol = next(v for v in pod['volumes'] if v['name'] == 'hermes-secrets-files')
    assert vol['secret']['secretName'] == 'hermes-secrets'
    main = next(c for c in pod['containers'] if c['name'] == 'hermes')
    assert any(m['mountPath'] == '/etc/hermes-secrets' for m in main['volumeMounts'])
    assert any(m['mountPath'] == '/etc/hermes-env' for m in main['volumeMounts'])
    env_names = {e['name'] for e in main.get('env', [])}
    assert not env_names & {'SEARXNG_URL', 'HASS_URL', 'HINDSIGHT_API_URL'}, 'keep service URLs in hermes-profile-env'
    # Same layout kubelet writes: key files plus dot-dirs the helper must skip.
    sec, envd = tmp_path / 'sec', tmp_path / 'env'
    for d in (sec, envd):
        (d / '..data').mkdir(parents=True)
    (sec / 'LITELLM_API_KEY').write_text('fake-1')
    (envd / 'SEARXNG_URL').write_text('http://s')
    cmd = helper.replace('/etc/hermes-secrets', str(sec)).replace('/etc/hermes-env', str(envd))
    out = subprocess.check_output(['/bin/sh', '-c', cmd], text=True)
    assert sorted(out.splitlines()) == ['LITELLM_API_KEY=fake-1', 'SEARXNG_URL=http://s']
