import importlib.util
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from zoneinfo import ZoneInfo

MODULE = Path(__file__).resolve().parents[1] / 'scripts/power-analysis/analysis.py'
spec = importlib.util.spec_from_file_location('analysis', MODULE)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def fixture(today=date(2026, 9, 27), days=8):
    rows = []
    start = a.midnight(today - timedelta(days=days), ZoneInfo('America/Detroit'))
    end = a.midnight(today, ZoneInfo('America/Detroit'))
    for key, entity in a.SERIES.items():
        for i, ts in enumerate(range(start - 3600, end, 3600)):
            rows.append({'statistic_id': entity, 'start_ts': ts,
                         'sum': i * (0.02 if key == 'gaming' else 0.1), 'state': None})
    for offset in range(days):
        ts = a.midnight(today - timedelta(days=offset + 1), ZoneInfo('America/Detroit'))
        for key, entity in a.GRID.items():
            rows.append({'statistic_id': entity, 'start_ts': ts,
                         'sum': 0, 'state': 30 if key == 'house' else 6})
    return rows


class PowerAnalysisTest(unittest.TestCase):
    def analyze(self, rows, **kwargs):
        return a.analyze(rows, kwargs.pop('today', date(2026, 9, 27)),
                         'America/Detroit', kwargs.pop('rate', 0.2), **kwargs)

    def test_energy_units_and_no_double_counting(self):
        report = self.analyze(fixture())
        self.assertEqual(report['sample_days'], 8)
        self.assertEqual(report['devices'][0]['average_w'], 100)
        self.assertEqual(report['devices'][0]['cost_30d'], 14.4)
        self.assertEqual(report['plug_30d_cost'], 100.8)
        self.assertEqual(report['non_session_pct'], 80)
        self.assertEqual(report['model_rate_difference_pct'], 0)
        self.assertIsNone(report['cooling_house_r'])

    def test_missing_hour_excluded_even_with_valid_boundaries(self):
        rows = fixture()
        rows.remove(next(r for r in rows if r['statistic_id'] == a.SERIES['threadripper'] and r['start_ts'] == a.midnight(date(2026, 9, 20), ZoneInfo('America/Detroit')) + 3600))
        report = self.analyze(rows)
        self.assertEqual(report['sample_days'], 7)
        self.assertTrue(any(d['date'] == '2026-09-20' and 'incomplete' in d['reason'] for d in report['excluded']))

    def test_midday_reset_excluded_even_if_day_net_is_positive(self):
        rows = fixture()
        ts = a.midnight(date(2026, 9, 20), ZoneInfo('America/Detroit')) + 3600
        next(r for r in rows if r['statistic_id'] == a.SERIES['threadripper'] and r['start_ts'] == ts)['sum'] = 0
        report = self.analyze(rows)
        self.assertTrue(any(d['date'] == '2026-09-20' and 'discontinuity' in d['reason'] for d in report['excluded']))

    def test_utility_date_must_match(self):
        rows = [r for r in fixture() if not (r['statistic_id'] == a.GRID['house'] and r['start_ts'] == a.midnight(date(2026, 9, 26), ZoneInfo('America/Detroit')))]
        self.assertEqual(self.analyze(rows)['sample_days'], 7)

    def test_today_never_used(self):
        rows = fixture(today=date(2026, 9, 28))
        report = self.analyze(rows)
        self.assertTrue(all(d['date'] < '2026-09-27' for d in report['days']))

    def test_dst_days_preserve_average_watts(self):
        for today, hours in [(date(2026, 3, 9), 23), (date(2026, 11, 2), 25)]:
            report = self.analyze(fixture(today, 1), today=today, lookback=1)
            self.assertEqual(report['sample_days'], 1)
            self.assertEqual(report['days'][0]['hours'], hours)
            self.assertEqual(report['devices'][0]['average_w'], 100)

    def test_unknown_price_does_not_become_zero_cost(self):
        for rate in (None, float('nan'), 0, -1):
            report = self.analyze(fixture(), rate=rate)
            self.assertEqual(report['sample_days'], 8)
            self.assertIsNone(report['plug_30d_cost'])
            self.assertIsNone(report['devices'][0]['cost_30d'])

    def test_empty_history_has_no_fabricated_findings(self):
        report = self.analyze([])
        self.assertEqual(report['sample_days'], 0)
        self.assertEqual(report['devices'], [])
        self.assertIsNone(report['non_session_pct'])
        self.assertIsNone(report['largest_other_day'])

    def test_fit_requires_sample_size_and_runtime_variation(self):
        self.assertEqual(a.fit([0, 1, 2], [1, 3, 5]), (None, None))
        self.assertEqual(a.fit([1] * 8, [1] * 8), (None, None))
        self.assertEqual(a.fit(list(range(8)), [2*x+15 for x in range(8)]), (1.0, 2000))

    def test_nonfinite_history_is_excluded(self):
        rows = fixture()
        rows[2]['sum'] = float('inf')
        self.assertLess(self.analyze(rows)['sample_days'], 8)

    def test_sqlite_reader_and_missing_db_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recorder.db'
            with self.assertRaises(FileNotFoundError):
                a.read_report(path, date(2026, 9, 27), 'America/Detroit', 0.2)
            self.assertFalse(path.exists())
            with sqlite3.connect(path) as db:
                db.executescript('CREATE TABLE statistics_meta(id INTEGER,statistic_id TEXT); CREATE TABLE statistics(metadata_id INTEGER,start_ts REAL,state REAL,sum REAL);')
                ids = {entity: i for i, entity in enumerate((*a.SERIES.values(), *a.GRID.values()))}
                db.executemany('INSERT INTO statistics_meta VALUES (?,?)', [(i,e) for e,i in ids.items()])
                db.executemany('INSERT INTO statistics VALUES (?,?,?,?)', [(ids[r['statistic_id']],r['start_ts'],r['state'],r['sum']) for r in fixture()])
            before = path.read_bytes()
            report = a.read_report(path, date(2026, 9, 27), 'America/Detroit', 0.2)
            self.assertEqual(report['sample_days'], 8)
            self.assertEqual(before, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
