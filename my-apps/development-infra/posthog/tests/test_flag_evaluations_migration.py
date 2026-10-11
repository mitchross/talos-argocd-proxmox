"""Check migration placement, recreation order, and compatibility guard boundaries."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "flag_evaluations_patch", ROOT / "scripts/patch-flag-evaluations-migration.py"
)
migration_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration_patch)
SOURCE = (ROOT / "tests/fixtures/flag_evaluations_migration.py").read_text()


def load_operations(source):
    sql = types.ModuleType("posthog.models.flag_evaluations.sql")
    for name, value in {
        "FLAG_EVALUATIONS_DATA_TABLE": "sharded_flag_evaluations",
        "FLAG_EVALUATIONS_TABLE": "flag_evaluations",
        "FLAG_EVALUATIONS_WRITABLE_TABLE": "writable_flag_evaluations",
        "FLAG_EVALUATIONS_MV_TABLE": "flag_evaluations_mv",
        "KAFKA_FLAG_EVALUATIONS_TABLE": "kafka_flag_evaluations",
        "KAFKA_FLAG_EVALUATIONS_TABLE_SQL": lambda: "CREATE TABLE kafka_flag_evaluations",
        "FLAG_EVALUATIONS_MV_SQL": lambda: "CREATE MATERIALIZED VIEW flag_evaluations_mv",
    }.items():
        setattr(sql, name, value)
    modules = {
        "posthog.clickhouse.client.connection": types.SimpleNamespace(
            NodeRole=types.SimpleNamespace(DATA="data", INGESTION_MEDIUM="ingestion-medium")
        ),
        "posthog.clickhouse.client.migration_tools": types.SimpleNamespace(
            run_sql_with_exceptions=lambda query, **kwargs: (query, kwargs)
        ),
        "posthog.models.flag_evaluations.sql": sql,
    }
    namespace = {}
    with patch.dict(sys.modules, modules):
        exec(compile(source, "0353_flag_evaluations_person_columns.py", "exec"), namespace)
    return namespace["operations"]


class FlagEvaluationsMigrationTests(unittest.TestCase):
    def test_defaults_run_after_adds_and_before_upstream_recreation(self):
        original = load_operations(SOURCE)
        patched = load_operations(migration_patch.patch_source(SOURCE))
        self.assertEqual(len(patched), 10)
        self.assertEqual(patched[6:], original[3:])
        tables = ("sharded_flag_evaluations", "flag_evaluations", "writable_flag_evaluations")
        for index, table in enumerate(tables):
            with self.subTest(table=table):
                add_sql, add_options = patched[index]
                default_sql, default_options = patched[index + 3]
                self.assertEqual(add_sql, original[index][0].removesuffix(
                    ", MODIFY COLUMN person_properties DEFAULT '{}'"
                ))
                self.assertEqual(default_sql, f"ALTER TABLE {table} MODIFY COLUMN person_properties DEFAULT '{{}}'")
                self.assertEqual(add_options, original[index][1])
                self.assertEqual(default_options, original[index][1])

    def test_patch_is_idempotent(self):
        patched = migration_patch.patch_source(SOURCE)
        self.assertEqual(migration_patch.patch_source(patched), patched)

    def test_changed_column_type_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "changed"):
            migration_patch.patch_source(SOURCE.replace("DateTime64(3)", "DateTime64(6)"))

    def test_changed_upstream_recreation_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "changed"):
            migration_patch.patch_source(SOURCE.replace("DROP TABLE IF EXISTS", "DROP TABLE"))

    def test_changed_patched_default_fails_closed(self):
        patched = migration_patch.patch_source(SOURCE).replace(
            "MODIFY COLUMN person_properties DEFAULT '{{}}'", "MODIFY COLUMN person_properties DEFAULT ''"
        )
        with self.assertRaisesRegex(RuntimeError, "changed"):
            migration_patch.patch_source(patched)


if __name__ == "__main__":
    unittest.main()
