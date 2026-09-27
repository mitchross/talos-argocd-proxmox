import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/consumers-energy-restore/snapshot.py'
spec = importlib.util.spec_from_file_location('snapshot', MODULE)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class States:
    def __init__(self):
        self.values = {}
        self.writes = []

    def get(self, entity):
        return self.values.get(entity)

    def async_set(self, entity, state, attrs):
        self.values[entity] = SimpleNamespace(state=state, attributes=attrs)
        self.writes.append(entity)


class UtilityRestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'recorder.db'
        self.hass = SimpleNamespace(states=States())
        with sqlite3.connect(self.path) as db:
            db.executescript('''
                CREATE TABLE states_meta (metadata_id INTEGER PRIMARY KEY, entity_id TEXT);
                CREATE TABLE state_attributes (attributes_id INTEGER PRIMARY KEY, shared_attrs TEXT);
                CREATE TABLE states (state_id INTEGER PRIMARY KEY, metadata_id INTEGER,
                                     state TEXT, last_updated_ts REAL, attributes_id INTEGER);
            ''')
            attrs = json.dumps({'friendly_name': 'CE fixture', 'unit_of_measurement': 'kWh'})
            db.execute('INSERT INTO state_attributes VALUES (1, ?)', (attrs,))
            for index, entity in enumerate(snapshot.ENTITIES, 1):
                db.execute('INSERT INTO states_meta VALUES (?, ?)', (index, entity))
                value = '2026-09-26' if entity.endswith('_last_reading') else str(index)
                db.execute('INSERT INTO states VALUES (?, ?, ?, ?, 1)', (index, index, value, index))
            db.execute("INSERT INTO states VALUES (50, 1, '34.924', 50, 1)")
            db.execute("INSERT INTO states VALUES (51, 1, 'unavailable', 51, 1)")

    def test_restores_last_valid_readings_and_preserves_date(self):
        data = snapshot.load_snapshot(self.path)
        self.assertEqual(len(data), 9)
        self.assertEqual(data[snapshot.ENTITIES[0]][0], '34.924')
        self.assertEqual(snapshot.restore_snapshot(self.hass, data), 9)
        self.assertEqual(self.hass.states.get(snapshot.ENTITIES[-1]).state, '2026-09-26')
        self.assertEqual(self.hass.states.writes[-1], snapshot.ENTITIES[-1])
        self.assertEqual(snapshot.restore_snapshot(self.hass, data), 0)

    def test_new_import_wins_over_startup_snapshot(self):
        self.hass.states.async_set(snapshot.ENTITIES[0], '42', {})
        self.hass.states.writes.clear()
        self.assertEqual(snapshot.restore_snapshot(self.hass, snapshot.load_snapshot(self.path)), 0)
        self.assertEqual(self.hass.states.writes, [])
        self.assertEqual(self.hass.states.get(snapshot.ENTITIES[0]).state, '42')

    def test_partial_recorded_batch_does_not_publish_a_freshness_date(self):
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM states WHERE metadata_id=2')
        self.assertEqual(snapshot.load_snapshot(self.path), {})

    def test_unknown_runtime_states_are_replaced(self):
        self.hass.states.async_set(snapshot.ENTITIES[0], 'unknown', {})
        self.assertEqual(snapshot.restore_snapshot(self.hass, snapshot.load_snapshot(self.path)), 9)

    def test_invalid_reading_date_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE states SET state='bad-date' WHERE metadata_id=9")
        with self.assertRaises(ValueError):
            snapshot.load_snapshot(self.path)

    def test_nonfinite_value_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE states SET state='nan' WHERE state_id=50")
        with self.assertRaises(ValueError):
            snapshot.load_snapshot(self.path)

    def test_missing_database_is_not_created(self):
        missing = self.path.parent / 'missing.db'
        self.assertEqual(snapshot.load_snapshot(missing), {})
        self.assertFalse(missing.exists())

    def test_only_importer_owned_states_are_selected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO states_meta VALUES (20,'sensor.consumers_energy_effective_rate')")
            db.execute("INSERT INTO states VALUES (60,20,'0.21',60,1)")
        self.assertNotIn('sensor.consumers_energy_effective_rate', snapshot.load_snapshot(self.path))


if __name__ == '__main__':
    unittest.main()
