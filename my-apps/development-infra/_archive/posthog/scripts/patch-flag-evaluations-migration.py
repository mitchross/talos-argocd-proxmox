"""Split migration 0353's ADD and MODIFY for ClickHouse's legacy analyzer."""

import ast
import hashlib
import sys
from pathlib import Path

# Migration from PostHog 5943705e66c26e44fd4da095e3710b20d12f4cfe; review on upgrades.
UPSTREAM_AST_SHA256 = "5421abf534a412ae1b1e5180f293f1e3f6274549afa413703c7ed383182d04b0"
ORIGINAL_SUFFIX = (
    '"ADD COLUMN IF NOT EXISTS person_mode Enum8(\'full\' = 0, \'propertyless\' = 1, \'force_upgrade\' = 2) AFTER inserted_at, "\n'
    '        "MODIFY COLUMN person_properties DEFAULT \'{}\'"'
)
SPLIT_SUFFIX = (
    '"ADD COLUMN IF NOT EXISTS person_mode Enum8(\'full\' = 0, \'propertyless\' = 1, \'force_upgrade\' = 2) AFTER inserted_at"'
)
DEFAULT_OPERATIONS = '''

# Apply defaults after all ADDs succeed, before the upstream Kafka/MV recreation.
operations[3:3] = [
    run_sql_with_exceptions(
        f"ALTER TABLE {table} MODIFY COLUMN person_properties DEFAULT '{{}}'",
        node_roles=node_roles,
        sharded=sharded,
        is_alter_on_replicated_table=replicated,
    )
    for table, node_roles, sharded, replicated in (
        (FLAG_EVALUATIONS_DATA_TABLE, [NodeRole.DATA], True, True),
        (FLAG_EVALUATIONS_TABLE, [NodeRole.DATA], False, False),
        (FLAG_EVALUATIONS_WRITABLE_TABLE, [NodeRole.INGESTION_MEDIUM], False, False),
    )
]
'''


def patch_source(source):
    original = source
    if source.endswith(DEFAULT_OPERATIONS):
        original = source[:-len(DEFAULT_OPERATIONS)].replace(SPLIT_SUFFIX, ORIGINAL_SUFFIX, 1)
    # Python 3.13+ omits empty lists by default; retain the reviewed 3.12 fingerprint.
    options = {"show_empty": True} if sys.version_info >= (3, 13) else {}
    tree = ast.dump(ast.parse(original), include_attributes=False, **options)
    if hashlib.sha256(tree.encode()).hexdigest() != UPSTREAM_AST_SHA256:
        raise RuntimeError("PostHog migration 0353 changed; review compatibility patch")
    if original.count(ORIGINAL_SUFFIX) != 1:
        raise RuntimeError("PostHog migration 0353 anchor changed; review compatibility patch")
    patched = original.replace(ORIGINAL_SUFFIX, SPLIT_SUFFIX, 1) + DEFAULT_OPERATIONS
    ast.parse(patched)
    return patched


if __name__ == "__main__":
    path = Path("/code/posthog/clickhouse/migrations/0353_flag_evaluations_person_columns.py")
    original = path.read_text()
    patched = patch_source(original)
    if patched != original:
        path.write_text(patched)
    print("ClickHouse migration 0353 compatibility check passed")
