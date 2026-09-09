import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('recover-index.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
ERROR = 'ord() expected a character, but string of length 0 found'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = self.root / '.flatnotes'
        self.index.mkdir()
        (self.index / '_5_1.toc').write_bytes(b'')
        (self.root / 'note.md').write_text('preserve my note')
        self.opener = Mock(side_effect=TypeError(ERROR))

    def test_preserves_original_and_notes(self):
        recovery.recover(self.root, self.opener)
        self.assertFalse(self.index.exists())
        archive = self.root / '.flatnotes-recovery-20260909'
        self.assertEqual((archive / 'index/_5_1.toc').read_bytes(), b'')
        self.assertTrue((archive / 'sha256.json').exists())
        self.assertEqual((self.root / 'note.md').read_text(), 'preserve my note')
        recovery.recover(self.root, self.opener)
        self.assertEqual(self.opener.call_count, 1)

    def test_healthy_index_unchanged(self):
        opener = Mock()
        recovery.recover(self.root, opener)
        opener.return_value.close.assert_called_once()
        self.assertTrue(self.index.exists())

    def test_other_failure_is_not_repaired(self):
        with self.assertRaises(TypeError):
            recovery.recover(self.root, Mock(side_effect=TypeError('different error')))
        self.assertTrue(self.index.exists())

    def test_existing_archive_not_overwritten(self):
        (self.root / '.flatnotes-recovery-20260909').mkdir()
        with self.assertRaises(FileExistsError):
            recovery.recover(self.root, self.opener)
        self.assertTrue(self.index.exists())

    def test_symlink_rejected(self):
        (self.index / 'link').symlink_to(self.root / 'note.md')
        with self.assertRaises(RuntimeError):
            recovery.recover(self.root, self.opener)
        self.assertTrue(self.index.exists())

    def test_low_space_preserves_original(self):
        with patch.object(recovery.shutil, 'disk_usage', return_value=Mock(free=0)):
            with self.assertRaises(RuntimeError):
                recovery.recover(self.root, self.opener)
        self.assertTrue(self.index.exists())

    def test_manifest_write_failure_leaves_original(self):
        with patch.object(recovery.json, 'dump', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                recovery.recover(self.root, self.opener)
        self.assertTrue(self.index.exists())


if __name__ == '__main__':
    unittest.main()
