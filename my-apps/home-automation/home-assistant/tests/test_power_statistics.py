import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/repair-power-statistics.py'
spec = importlib.util.spec_from_file_location('repair', MODULE)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class StatisticsRepairTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'recorder.db'
        self.backup = Path(self.tmp.name) / 'backup.json'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE statistics_meta (id INTEGER PRIMARY KEY, statistic_id TEXT)')
            db.executemany('INSERT INTO statistics_meta VALUES (?,?)',[
                (1,'sensor.homelab_total_energy'), (2,'consumers_energy:grid_kwh')])
            for table in repair.TABLES:
                db.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, metadata_id INTEGER, start_ts REAL, state REAL, sum REAL)')
                db.executemany(f'INSERT INTO {table} VALUES (?,?,?,?,?)',[
                    (1,1,repair.PREVIOUS,247,104.892),
                    (2,1,repair.BOUNDARY,252.296,0.309),
                    (3,1,repair.BOUNDARY+3600,252.834,0.847),
                    (4,2,repair.BOUNDARY,900,800)])

    def run_repair(self,apply=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return repair.repair(self.path,self.backup,apply)

    def values(self):
        with sqlite3.connect(self.path) as db:
            return db.execute('SELECT * FROM statistics ORDER BY id').fetchall()

    def test_restores_continuity_preserves_readings_and_other_series(self):
        before=self.values()
        self.assertEqual(len(self.run_repair()),1)
        after=self.values()
        self.assertEqual(before[0],after[0])
        self.assertEqual(before[3],after[3])
        self.assertEqual(before[1][:-1],after[1][:-1])
        self.assertAlmostEqual(after[1][-1]-after[0][-1],252.296-247)
        self.assertAlmostEqual(after[2][-1]-after[1][-1],0.538)
        self.assertEqual(self.run_repair(),[])
        journal=json.loads(self.backup.read_text())
        self.assertEqual(journal['originals']['statistics'][0][-1],0.309)
        with sqlite3.connect(self.path) as db:
            self.assertAlmostEqual(db.execute('SELECT sum FROM statistics_short_term WHERE id=2').fetchone()[0],after[1][-1])

    def test_dry_run_does_not_mutate_or_write_backup(self):
        before=self.values()
        self.assertEqual(len(self.run_repair(False)),1)
        self.assertEqual(self.values(),before)
        self.assertFalse(self.backup.exists())

    def test_unexpected_decrease_fails_without_mutation(self):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE statistics SET state=1 WHERE id=2')
        before=self.values()
        with self.assertRaises(ValueError):self.run_repair()
        self.assertEqual(self.values(),before)
        self.assertFalse(self.backup.exists())

    def test_retry_after_journal_written_before_commit(self):
        self.run_repair()
        journal=json.loads(self.backup.read_text())
        with sqlite3.connect(self.path) as db:
            for table,rows in journal['originals'].items():
                db.executemany(f'UPDATE {table} SET sum=? WHERE id=?',[(r[3],r[0]) for r in rows])
        self.assertEqual(len(self.run_repair()),1)
        self.assertEqual(self.run_repair(),[])

    def test_conflicting_journal_is_not_overwritten(self):
        self.backup.write_text('{}')
        before=self.values()
        with self.assertRaises(ValueError):self.run_repair()
        self.assertEqual(self.values(),before)
        self.assertEqual(self.backup.read_text(),'{}')

    def test_undo_restores_baseline_including_new_rows(self):
        before=self.values()
        self.run_repair()
        with sqlite3.connect(self.path) as db:
            last=db.execute('SELECT sum FROM statistics WHERE id=3').fetchone()[0]
            db.execute('INSERT INTO statistics VALUES (5,1,?,?,?)',
                       (repair.BOUNDARY+7200,253,last+0.166))
        with contextlib.redirect_stdout(io.StringIO()):repair.undo(self.path,self.backup)
        after=self.values()
        for old,new in zip(before,after):
            self.assertEqual(old[:-1],new[:-1])
            self.assertAlmostEqual(old[-1],new[-1])
        self.assertAlmostEqual(after[-1][-1],1.013)
        with contextlib.redirect_stdout(io.StringIO()):repair.undo(self.path,self.backup)
        self.assertEqual(self.values(),after)

    def test_no_matching_boundary_is_a_noop(self):
        with sqlite3.connect(self.path) as db:db.execute('DELETE FROM statistics WHERE id=1')
        self.assertEqual(self.run_repair(),[])
        self.assertFalse(self.backup.exists())


if __name__ == '__main__':
    unittest.main()
