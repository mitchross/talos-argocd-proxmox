import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('worker_ready', HERE / 'worker-ready.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerReadinessTests(unittest.TestCase):
    def test_requires_this_worker_pong(self):
        app = Mock()
        app.control.inspect.return_value.ping.return_value = {'celery@other': {'ok': 'pong'}}
        self.assertFalse(worker.ready(app, 'ours'))
        app.control.inspect.return_value.ping.return_value = {'celery@ours': {'ok': 'pong'}}
        self.assertTrue(worker.ready(app, 'ours'))
        app.control.inspect.assert_called_with(destination=['celery@ours'], timeout=3)

    def test_no_reply_is_not_ready(self):
        app = Mock()
        app.control.inspect.return_value.ping.return_value = None
        self.assertFalse(worker.ready(app, 'ours'))


class AofRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.aof = self.root / 'appendonlydir'
        self.aof.mkdir()
        self.tail = self.aof / 'appendonly.aof.3.incr.aof'
        with self.tail.open('wb') as stream:
            stream.truncate(36162313)
        (self.aof / 'appendonly.aof.manifest').write_text('manifest fixture')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, REDIS_DATA_DIR=str(self.root),
                        PATH=str(self.bin) + ':' + os.environ['PATH'])
        self.checker = self.bin / 'redis-check-aof'
        self.checker.write_text('''#!/bin/sh
if [ "$1" = --fix ]; then
  truncate -s 36151654 appendonlydir/appendonly.aof.3.incr.aof
  exit 0
fi
size=$(wc -c < appendonlydir/appendonly.aof.3.incr.aof)
[ "$size" -eq 36151654 ] && exit 0
echo 'AOF analyzed: filename=appendonly.aof.3.incr.aof, size=36162313, ok_up_to=36151654, ok_up_to_line=10, diff=10659'
exit 1
''')
        self.checker.chmod(0o755)

    def run_script(self):
        return subprocess.run(['sh', str(HERE / 'recover-redis-aof.sh')], env=self.env,
                              capture_output=True, text=True)

    def test_preserves_then_truncates_and_reruns_safely(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        original = self.root / 'redis-aof-recovery-20260909/original' / self.tail.name
        self.assertEqual(original.stat().st_size, 36162313)
        self.assertEqual(self.tail.stat().st_size, 36151654)
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(original.stat().st_size, 36162313)

    def test_different_size_not_modified(self):
        self.tail.write_bytes(b'unexpected')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.read_bytes(), b'unexpected')

    def test_different_checker_offset_not_modified(self):
        self.checker.write_text(self.checker.read_text().replace('ok_up_to=36151654', 'ok_up_to=5'))
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.stat().st_size, 36162313)

    def test_prior_archive_not_overwritten(self):
        (self.root / 'redis-aof-recovery-20260909').mkdir()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.stat().st_size, 36162313)

    def test_copy_failure_never_repairs(self):
        fake = self.bin / 'cp'
        fake.write_text('#!/bin/sh\nexit 1\n')
        fake.chmod(0o755)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.stat().st_size, 36162313)

    def test_comparison_failure_never_repairs(self):
        fake = self.bin / 'cmp'
        fake.write_text('#!/bin/sh\nexit 1\n')
        fake.chmod(0o755)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.stat().st_size, 36162313)

    def test_hidden_file_is_not_silently_omitted(self):
        (self.aof / '.unexpected').write_bytes(b'preserve')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.stat().st_size, 36162313)
        self.assertEqual((self.aof / '.unexpected').read_bytes(), b'preserve')

    def test_low_space_never_repairs(self):
        fake = self.bin / 'df'
        fake.write_text('#!/bin/sh\necho "disk 100 100 0 100% /"\n')
        fake.chmod(0o755)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.stat().st_size, 36162313)

    def test_symlink_never_repairs(self):
        (self.aof / 'link').symlink_to(self.tail)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.tail.stat().st_size, 36162313)


if __name__ == '__main__':
    unittest.main()
