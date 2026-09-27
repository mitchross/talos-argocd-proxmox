#!/usr/bin/env python3
"""Repair the verified 2026-09-24 statistics restart, with HA stopped."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import sqlite3

# Both sides of this gap are on September 24 in the HA timezone; no meter cycle resets.
BOUNDARY = 1790290800  # 2026-09-24 23:00 UTC, first restored hourly bucket
PREVIOUS = 1790258400  # 2026-09-24 14:00 UTC, last surviving hourly bucket
PATTERN = re.compile(
    r"sensor\.(?:threadripper|nas_psu|truenas|hp_sff|hp_elite|gaming_pc|"
    r"gaming_pc_gaming|macbook|shed_lab|homelab(?:_total)?|office(?:_total)?|"
    r"combined(?:_total)?|ac_cooling)_(?:energy|cost|hours)"
    r"(?:_(?:daily|weekly|monthly|yearly))?\Z"
)
TABLES = ("statistics", "statistics_short_term")


def plan_repairs(db):
    plans = []
    for meta, entity in db.execute("SELECT id, statistic_id FROM statistics_meta"):
        if not PATTERN.fullmatch(entity):
            continue
        before = db.execute(
            "SELECT state, sum FROM statistics WHERE metadata_id=? AND start_ts=?",
            (meta, PREVIOUS),
        ).fetchone()
        after = db.execute(
            "SELECT state, sum FROM statistics WHERE metadata_id=? AND start_ts=?",
            (meta, BOUNDARY),
        ).fetchone()
        if before is None or after is None:
            continue
        if any(v is None or not math.isfinite(v) for v in (*before, *after)):
            raise ValueError(f"Non-numeric boundary values: {entity}")
        offset = before[1] + after[0] - before[0] - after[1]
        if abs(offset) < 0.00001:
            continue
        if offset < 0 or after[0] < before[0] or after[1] >= before[1]:
            raise ValueError(f"Unexpected boundary for {entity}; refusing automatic repair")
        plans.append({"metadata_id": meta, "entity": entity, "offset": offset})
    return plans


def repair(path, backup, apply=False):
    with sqlite3.connect(f"file:{path}?mode={'rw' if apply else 'ro'}", uri=True) as db:
        if apply:
            db.execute("BEGIN IMMEDIATE")
        plans = plan_repairs(db)
        print(json.dumps({"apply": apply, "repairs": plans}, indent=2))
        if not apply or not plans:
            return plans
        backup = Path(backup)
        backup.parent.mkdir(parents=True, exist_ok=True)
        # Journal only affected statistics, not the multi-GB recorder state history.
        originals = {table: [] for table in TABLES}
        for item in plans:
            for table in TABLES:
                originals[table].extend(db.execute(
                    f"SELECT id, metadata_id, start_ts, sum FROM {table} "
                    "WHERE metadata_id=? AND start_ts>=? AND sum IS NOT NULL",
                    (item['metadata_id'], BOUNDARY),
                ).fetchall())
        journal = {"version": 1, "boundary": BOUNDARY, "plans": plans, "originals": originals}
        if backup.exists():
            saved = json.loads(backup.read_text())
            if saved != json.loads(json.dumps(journal)):
                raise ValueError("Existing repair journal differs from this database")
        else:
            temporary = backup.with_suffix('.tmp')
            with temporary.open('w') as output:
                os.chmod(temporary, 0o600)
                json.dump(journal, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(backup)
        for item in plans:
            for table in TABLES:
                db.execute(
                    f"UPDATE {table} SET sum=sum+? WHERE metadata_id=? AND start_ts>=?",
                    (item['offset'], item['metadata_id'], BOUNDARY),
                )
        if plan_repairs(db):
            raise ValueError("Continuity check failed; transaction rolled back")
        db.commit()
        print(f"Repaired {len(plans)} series; originals saved in {backup}")
        return plans


def same_plans(actual, expected):
    return len(actual) == len(expected) and all(
        a['metadata_id'] == b['metadata_id'] and a['entity'] == b['entity']
        and math.isclose(a['offset'], b['offset'], abs_tol=1e-8)
        for a, b in zip(actual, expected)
    )


def undo(path, backup):
    journal = json.loads(Path(backup).read_text())
    if journal.get('version') != 1 or journal.get('boundary') != BOUNDARY:
        raise ValueError("Unsupported repair journal")
    with sqlite3.connect(f"file:{path}?mode=rw", uri=True) as db:
        db.execute("BEGIN IMMEDIATE")
        pending = plan_repairs(db)
        if pending:
            if same_plans(pending, journal['plans']):
                print('Repair is already undone')
                return
            raise ValueError("Database no longer matches the recorded repair")
        for item in journal['plans']:
            entity = db.execute("SELECT statistic_id FROM statistics_meta WHERE id=?",
                                (item['metadata_id'],)).fetchone()
            if entity != (item['entity'],):
                raise ValueError("Statistic metadata changed; refusing undo")
            for table in TABLES:
                # New rows inherit the repaired baseline, so undo their offset too.
                db.execute(f"UPDATE {table} SET sum=sum-? WHERE metadata_id=? AND start_ts>=?",
                           (item['offset'], item['metadata_id'], BOUNDARY))
        if not same_plans(plan_repairs(db), journal['plans']):
            raise ValueError("Undo verification failed; transaction rolled back")
        db.commit()
        print('Statistics baseline restored; disable the repair init container before starting HA')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='/config/home-assistant_v2.db')
    parser.add_argument('--backup', default='/config/statistics-repairs/power-2026-09-24.json')
    parser.add_argument('--apply', action='store_true', help='Only while Home Assistant is stopped')
    parser.add_argument('--undo', action='store_true', help='Undo with HA stopped and the repair init container disabled in Git')
    args = parser.parse_args()
    if args.undo:
        if not args.apply:
            parser.error('--undo requires --apply')
        undo(args.database, args.backup)
        return
    if not Path(args.database).exists():
        print('No recorder database; nothing to repair')
        return
    repair(args.database, args.backup, args.apply)


if __name__ == '__main__':
    main()
