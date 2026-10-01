"""Exercise both actual entrypoints with payloads; never execute payload commands."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BranchGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'main checkout'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                 'commit', '--allow-empty', '-m', 'fixture')
        self.feature = Path(self.temp.name) / 'feature checkout'
        self.git('worktree', 'add', '-b', 'feature/test', str(self.feature))

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True)

    def decisions(self, command, cwd=None, codex=False):
        payload = {'cwd': str(cwd or self.repo), 'tool_input':
                   {('cmd' if codex else 'command'): command}, 'tool_name':
                   ('exec_command' if codex else 'Bash')}
        values = []
        for client in ['.claude', '.codex']:
            result = subprocess.run(['bash', str(ROOT / client / 'hooks/git-branch-guard.sh')],
                                    input=json.dumps(payload), capture_output=True, text=True, check=True)
            values.append(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision']
                          if result.stdout else None)
        self.assertEqual(values[0], values[1])
        self.assertNotIn('allow', values)
        return values[0]

    def test_default_writes(self):
        for cmd in ['git commit -m test', 'git push origin main', 'git -c user.name=test commit',
                    '/usr/bin/git commit', 'git push', 'git push origin HEAD:main']:
            with self.subTest(cmd=cmd):
                self.assertEqual('deny', self.decisions(cmd))

    def test_feature_targets(self):
        for ref in ['main', 'master', 'HEAD:main', '+HEAD:refs/heads/main', ':main',
                    'HEAD:refs/heads/master', '--all', '--mirror']:
            with self.subTest(ref=ref):
                self.assertEqual('deny', self.decisions(f'git push origin {ref}', self.feature))
        for cmd in ['git commit -m test', 'git push origin feature/test', 'git push',
                    'git commit -m test && kubectl delete namespace example']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decisions(cmd, self.feature))

    def test_worktree_global_options_and_cwd(self):
        feature = json.dumps(str(self.feature))
        main = json.dumps(str(self.repo))
        self.assertIsNone(self.decisions(f'git -C {feature} -c user.name=test commit -m test'))
        self.assertIsNone(self.decisions(f'cd {feature} && git commit -m test'))
        self.assertEqual('deny', self.decisions(f'git -C {feature} commit && git -C {main} commit'))
        self.assertEqual('deny', self.decisions(f'git -C {main} commit', self.feature))
        self.assertIsNone(self.decisions('git commit -m test', self.feature, codex=True))

    def test_configured_default_push(self):
        subprocess.run(['git', '-C', str(self.feature), 'config', 'branch.feature/test.merge',
                        'refs/heads/main'], check=True)
        self.assertEqual('deny', self.decisions('git push', self.feature))
        self.assertIsNone(self.decisions('git push origin HEAD:feature/test', self.feature))

    def test_wiring(self):
        for client, config in [('.claude', 'settings.json'), ('.codex', 'hooks.json')]:
            data = json.loads((ROOT / client / config).read_text())
            guards = [h for group in data['hooks']['PreToolUse'] if group.get('matcher') == 'Bash'
                      for h in group['hooks'] if 'git-branch-guard.sh' in h.get('command', '')]
            self.assertEqual(1, len(guards))
            self.assertNotIn('if', guards[0])


if __name__ == '__main__':
    unittest.main()
