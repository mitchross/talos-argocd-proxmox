#!/usr/bin/env python3
"""Archive retired completed-period statistics while Home Assistant is stopped."""

import argparse
import json
import os
from pathlib import Path
import sqlite3

import yaml

RETIRED = tuple('sensor.' + name for name in (
    'gaming_pc_gaming_cost_last_month', 'gaming_pc_gaming_hours_last_month',
    'ac_cooling_cost_yesterday', 'ac_cooling_cost_last_month',
    'ac_cooling_hours_yesterday', 'ac_cooling_hours_last_month', 'ac_cooling_energy_last_month',
    'homelab_cost_last_month', 'homelab_cost_yesterday', 'homelab_total_energy_last_month',
    'office_cost_last_month', 'office_cost_yesterday', 'office_total_energy_last_month',
    'combined_cost_last_month', 'combined_cost_yesterday', 'combined_total_energy_last_month',
    'threadripper_cost_last_month', 'threadripper_energy_last_month',
    'nas_psu_cost_last_month', 'nas_psu_energy_last_month',
    'truenas_cost_last_month', 'truenas_energy_last_month',
    'hp_sff_cost_last_month', 'hp_sff_energy_last_month',
    'hp_elite_cost_last_month', 'hp_elite_energy_last_month',
    'gaming_pc_cost_last_month', 'gaming_pc_energy_last_month',
    'macbook_cost_last_month', 'macbook_energy_last_month', 'shed_lab_energy_last_month',
    'homelab_total_energy_yesterday', 'combined_total_energy_yesterday',
))
TABLES = ('statistics_meta', 'statistics', 'statistics_short_term')
MARKERS = ','.join('?' for _ in RETIRED)


def verify_config(config):
    root = Path(config)
    data = yaml.load((root / 'configuration.yaml').read_text(), Loader=yaml.BaseLoader)
    sensors = {}
    for block in data.get('template', []):
        if isinstance(block, dict):
            for sensor in block.get('sensor', []):
                if isinstance(sensor, dict) and sensor.get('unique_id'):
                    sensors.setdefault('sensor.' + sensor['unique_id'], []).append(sensor)
    custom = yaml.load((root / 'customize.yaml').read_text(), Loader=yaml.BaseLoader) or {}
    for entity in RETIRED:
        matches = sensors.get(entity, [])
        if len(matches) != 1 or 'state_class' in matches[0] or 'state_class' in custom.get(entity, {}):
            raise ValueError(f'{entity} is not an unambiguous retired template; refusing cleanup')


def snapshot(db):
    meta = db.execute(f'SELECT * FROM statistics_meta WHERE statistic_id IN ({MARKERS}) ORDER BY id', RETIRED)
    columns = [field[0] for field in meta.description]
    rows = [list(row) for row in meta]
    if any(row[columns.index('source')] != 'recorder' for row in rows):
        raise ValueError('Unexpected statistics source; refusing cleanup')
    result = {'version': 1, 'entities': list(RETIRED), 'tables': {
        'statistics_meta': {'columns': columns, 'rows': rows},
    }}
    for table in TABLES[1:]:
        cursor = db.execute(f'SELECT * FROM {table} WHERE metadata_id IN '
                            f'(SELECT id FROM statistics_meta WHERE statistic_id IN ({MARKERS})) ORDER BY id', RETIRED)
        result['tables'][table] = {'columns': [field[0] for field in cursor.description],
                                  'rows': [list(row) for row in cursor]}
    return result


def save_archive(path, data):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text()) != data:
            raise ValueError('Existing statistics archive differs; refusing overwrite')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as output:
        os.chmod(temporary, 0o600)
        json.dump(data, output, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def retire(database, archive, config, apply=False):
    verify_config(config)
    with sqlite3.connect(f'file:{database}?mode={"rw" if apply else "ro"}', uri=True) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
        saved = snapshot(db)
        counts = {table: len(saved['tables'][table]['rows']) for table in TABLES}
        print(json.dumps({'apply': apply, 'archive': str(archive), 'counts': counts}))
        if not apply or not counts['statistics_meta']:
            return counts
        save_archive(archive, saved)
        for table in TABLES[1:]:
            db.execute(f'DELETE FROM {table} WHERE metadata_id IN '
                       f'(SELECT id FROM statistics_meta WHERE statistic_id IN ({MARKERS}))', RETIRED)
        db.execute(f'DELETE FROM statistics_meta WHERE statistic_id IN ({MARKERS})', RETIRED)
        db.commit()
        return counts


def logical_rows(saved):
    tables = {table: [dict(zip(block['columns'], row, strict=True)) for row in block['rows']]
              for table, block in saved['tables'].items()}
    entities = {row['id']: row['statistic_id'] for row in tables['statistics_meta']}
    result = {}
    for table, rows in tables.items():
        for row in rows:
            row.pop('id')
            if 'metadata_id' in row:
                row['metadata_id'] = entities[row['metadata_id']]
        result[table] = sorted(json.dumps(row, sort_keys=True) for row in rows)
    return result


def restore(database, archive):
    saved = json.loads(Path(archive).read_text())
    if saved.get('version') != 1 or saved.get('entities') != list(RETIRED):
        raise ValueError('Unsupported statistics archive')
    with sqlite3.connect(f'file:{database}?mode=rw', uri=True) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        for table in TABLES:
            columns = [column[1] for column in db.execute(f'PRAGMA table_info({table})')]
            if columns != saved['tables'][table]['columns']:
                raise ValueError('Recorder schema changed; refusing restore')
        current = snapshot(db)
        if current['tables']['statistics_meta']['rows']:
            if logical_rows(current) == logical_rows(saved):
                print('Archived statistics already restored')
                return
            raise ValueError('Retired statistics already exist with different data; refusing restore')
        mapping = {}
        for table in TABLES:
            block = saved['tables'][table]
            for row in block['rows']:
                values = dict(zip(block['columns'], row, strict=True))
                old_id = values.pop('id')
                if table == 'statistics_meta':
                    if values['statistic_id'] not in RETIRED or values['source'] != 'recorder':
                        raise ValueError('Archive contains unexpected statistics')
                else:
                    values['metadata_id'] = mapping[values['metadata_id']]
                # HA may have reused old row IDs since retirement; allocate fresh ones.
                cursor = db.execute(f'INSERT INTO {table} ({",".join(values)}) '
                                    f'VALUES ({",".join("?" for _ in values)})', tuple(values.values()))
                if table == 'statistics_meta':
                    mapping[old_id] = cursor.lastrowid
        db.commit()
    print('Archived statistics restored; keep the retirement init container disabled in Git')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='/config/home-assistant_v2.db')
    parser.add_argument('--archive', default='/config/statistics-repairs/retired-period-summaries-2026-09-29.json')
    parser.add_argument('--config', default='/config')
    parser.add_argument('--apply', action='store_true', help='Only while HA is stopped')
    parser.add_argument('--restore', action='store_true', help='Restore offline with the retirement init disabled in Git')
    args = parser.parse_args()
    if args.restore:
        if not args.apply:
            parser.error('--restore requires --apply')
        restore(args.database, args.archive)
    elif Path(args.database).exists():
        retire(args.database, args.archive, args.config, args.apply)
    else:
        print('No recorder database; nothing to retire')


if __name__ == '__main__':
    main()
