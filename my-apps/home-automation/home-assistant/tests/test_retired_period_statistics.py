import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('retired', ROOT / 'scripts/retire-period-statistics.py')
retired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retired)


class RetiredStatisticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / 'recorder.db'
        self.archive = self.root / 'archive.json'
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE statistics_meta (id INTEGER PRIMARY KEY, statistic_id TEXT UNIQUE, source TEXT)')
            db.executemany('INSERT INTO statistics_meta VALUES (?,?,?)', [
                (1, retired.RETIRED[0], 'recorder'), (2, retired.RETIRED[-1], 'recorder'),
                (3, 'sensor.homelab_total_energy', 'recorder'),
                (4, 'consumers_energy:grid_kwh', 'consumers_energy'),
            ])
            for table in retired.TABLES[1:]:
                db.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, metadata_id INTEGER '
                           'REFERENCES statistics_meta(id), start_ts REAL, state REAL, sum REAL)')
                db.executemany(f'INSERT INTO {table} VALUES (?,?,?,?,?)', [
                    (1, 1, 1000, 3, 6), (2, 1, 2000, 4, 7),
                    (3, 2, 1000, 2, 5), (4, 3, 1000, 80, 80), (5, 4, 1000, 100, 100),
                ])
            db.execute('CREATE TABLE states (id INTEGER PRIMARY KEY, state TEXT)')
            db.execute("INSERT INTO states VALUES (1, 'keep raw readings')")

    def run_retire(self, apply=True, config=ROOT):
        with contextlib.redirect_stdout(io.StringIO()):
            return retired.retire(self.database, self.archive, config, apply)

    def contents(self):
        with sqlite3.connect(self.database) as db:
            return {table: db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
                    for table in (*retired.TABLES, 'states')}

    def test_allowlist_matches_exactly_33_retired_repo_templates(self):
        self.assertEqual(len(set(retired.RETIRED)), 33)
        retired.verify_config(ROOT)

    def test_archive_and_cleanup_preserve_active_statistics_and_all_raw_readings(self):
        before = self.contents()
        counts = self.run_retire()
        self.assertEqual(counts, {'statistics_meta': 2, 'statistics': 3, 'statistics_short_term': 3})
        after = self.contents()
        self.assertEqual(after['states'], before['states'])
        self.assertEqual(after['statistics_meta'], before['statistics_meta'][2:])
        for table in retired.TABLES[1:]:
            self.assertEqual(after[table], before[table][3:])
        saved = json.loads(self.archive.read_text())
        self.assertEqual(saved['tables']['statistics']['rows'], [list(row) for row in before['statistics'][:3]])
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
        original_archive = self.archive.read_bytes()
        self.assertEqual(self.run_retire()['statistics_meta'], 0)
        self.assertEqual(self.archive.read_bytes(), original_archive)

    def test_dry_run_is_read_only_and_writes_no_archive(self):
        before = self.contents()
        self.assertEqual(self.run_retire(False)['statistics_meta'], 2)
        self.assertEqual(self.contents(), before)
        self.assertFalse(self.archive.exists())

    def test_conflicting_archive_is_not_overwritten(self):
        before = self.contents()
        self.archive.write_text('{}')
        with self.assertRaises(ValueError):
            self.run_retire()
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.archive.read_text(), '{}')

    def test_archive_write_failure_prevents_deletion(self):
        before = self.contents()
        with patch.object(retired, 'save_archive', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.run_retire()
        self.assertEqual(self.contents(), before)

    def test_retry_after_archiving_before_database_commit(self):
        with sqlite3.connect(self.database) as db:
            retired.save_archive(self.archive, retired.snapshot(db))
        self.assertEqual(self.run_retire()['statistics_meta'], 2)

    def test_unexpected_source_fails_closed(self):
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE statistics_meta SET source='unexpected' WHERE id=1")
        before = self.contents()
        with self.assertRaises(ValueError):
            self.run_retire()
        self.assertEqual(self.contents(), before)

    def test_reintroduced_state_class_blocks_cleanup(self):
        for name in ('configuration.yaml', 'customize.yaml'):
            (self.root / name).write_text((ROOT / name).read_text())
        config = self.root / 'configuration.yaml'
        text = config.read_text().replace('unique_id: gaming_pc_gaming_cost_last_month',
                                         'unique_id: gaming_pc_gaming_cost_last_month\n        state_class: total')
        config.write_text(text)
        before = self.contents()
        with self.assertRaises(ValueError):
            self.run_retire(config=self.root)
        self.assertEqual(self.contents(), before)

    def test_restore_handles_reused_row_ids_and_is_idempotent(self):
        before = self.contents()
        self.run_retire()
        with sqlite3.connect(self.database) as db:
            db.execute("INSERT INTO statistics_meta VALUES (1, 'sensor.new_meter', 'recorder')")
            for table in retired.TABLES[1:]:
                db.execute(f'INSERT INTO {table} VALUES (1,1,3000,99,99)')
        with contextlib.redirect_stdout(io.StringIO()):
            retired.restore(self.database, self.archive)
        with sqlite3.connect(self.database) as db:
            for table in retired.TABLES[1:]:
                rows = db.execute(f'SELECT m.statistic_id, s.start_ts, s.state, s.sum FROM {table} s '
                                  'JOIN statistics_meta m ON m.id=s.metadata_id WHERE m.statistic_id IN (?,?) '
                                  'ORDER BY m.statistic_id,s.start_ts',
                                  (retired.RETIRED[0], retired.RETIRED[-1])).fetchall()
                expected = sorted((retired.RETIRED[0] if row[1] == 1 else retired.RETIRED[-1], *row[2:])
                                  for row in before[table][:3])
                self.assertEqual(rows, expected)
            self.assertEqual(db.execute('SELECT * FROM states').fetchall(), before['states'])
        after = self.contents()
        with contextlib.redirect_stdout(io.StringIO()):
            retired.restore(self.database, self.archive)
        self.assertEqual(self.contents(), after)

    def test_database_error_rolls_back_deletions_and_allows_retry(self):
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TRIGGER block_retirement BEFORE DELETE ON statistics_meta "
                       "BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
        before = self.contents()
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_retire()
        self.assertEqual(self.contents(), before)
        self.assertTrue(self.archive.exists())
        with sqlite3.connect(self.database) as db:
            db.execute('DROP TRIGGER block_retirement')
        self.assertEqual(self.run_retire()['statistics_meta'], 2)

    def test_restore_refuses_conflicting_existing_statistics(self):
        self.run_retire()
        with sqlite3.connect(self.database) as db:
            db.execute('INSERT INTO statistics_meta VALUES (1, ?, ?)', (retired.RETIRED[0], 'recorder'))
        before = self.contents()
        with self.assertRaises(ValueError):
            retired.restore(self.database, self.archive)
        self.assertEqual(self.contents(), before)

    def test_restore_schema_mismatch_leaves_database_unchanged(self):
        self.run_retire()
        with sqlite3.connect(self.database) as db:
            db.execute('ALTER TABLE statistics ADD COLUMN extra TEXT')
        before = self.contents()
        with self.assertRaises(ValueError):
            retired.restore(self.database, self.archive)
        self.assertEqual(self.contents(), before)


if __name__ == '__main__':
    unittest.main()
