"""Read-only, local-day power accounting shared by HA and agent reviews."""

import argparse
from datetime import date, datetime, time, timedelta
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean
from zoneinfo import ZoneInfo

DEVICES = {
    'threadripper': 'Threadripper + 2×3090',
    'truenas': 'TrueNAS DL360',
    'nas_psu': 'NAS drive PSU',
    'hp_sff': 'HP SFF + Optiplex',
    'hp_elite': 'HP Elite Mini',
    'gaming_pc': 'Gaming PC',
    'macbook': 'MacBook + monitor',
}
SERIES = {key: f'sensor.{key}_energy' for key in DEVICES}
SERIES.update({
    'homelab': 'sensor.homelab_total_energy',
    'office': 'sensor.office_total_energy',
    'gaming': 'sensor.gaming_pc_gaming_energy',
    'cooling_hours': 'sensor.ac_cooling_hours',
})
GRID = {'house': 'consumers_energy:grid_kwh', 'house_cost': 'consumers_energy:grid_cost'}


def number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def midnight(day, zone):
    return int(datetime.combine(day, time(), zone).timestamp())


def fit(xs, ys):
    if len(xs) < 7 or max(xs) - min(xs) < 1:
        return None, None
    mx, my = mean(xs), mean(ys)
    xx = sum((x - mx) ** 2 for x in xs)
    yy = sum((y - my) ** 2 for y in ys)
    xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return (round(xy / math.sqrt(xx * yy), 3) if yy else None), round(xy / xx * 1000)


def analyze(rows, today, timezone, rate, lookback=14):
    zone = ZoneInfo(timezone)
    indexed = {entity: {} for entity in (*SERIES.values(), *GRID.values())}
    for row in rows:
        if row['statistic_id'] in indexed:
            indexed[row['statistic_id']][int(row['start_ts'])] = dict(row)
    included, excluded = [], []
    for offset in range(lookback, 0, -1):
        day = today - timedelta(days=offset)
        start, end = midnight(day, zone), midnight(day + timedelta(days=1), zone)
        entry = {'date': day.isoformat(), 'hours': (end - start) / 3600}
        reason = None
        for key, entity in SERIES.items():
            samples = [indexed[entity].get(ts, {}).get('sum') for ts in range(start - 3600, end, 3600)]
            if not all(number(s) for s in samples):
                reason = f'{key}: incomplete hourly history'
                break
            if any(b < a - 0.00001 for a, b in zip(samples, samples[1:])):
                reason = f'{key}: counter discontinuity'
                break
            entry[key] = round(samples[-1] - samples[0], 5)
        if reason is None:
            for key, entity in GRID.items():
                value = indexed[entity].get(start, {}).get('state')
                if not number(value) or value < 0 or (key == 'house' and value == 0):
                    reason = 'utility report missing or invalid'
                    break
                entry[key] = value
        if reason is None and entry['gaming'] > entry['gaming_pc'] + 0.02:
            reason = 'gaming energy exceeds whole PC'
        if reason is None and entry['cooling_hours'] > entry['hours'] + 0.02:
            reason = 'cooling runtime exceeds day length'
        if reason:
            excluded.append({'date': day.isoformat(), 'reason': reason})
        else:
            included.append(entry)
    priced = number(rate) and rate > 0
    report = {
        'sample_days': len(included), 'window_start': (today - timedelta(days=lookback)).isoformat(),
        'window_end': (today - timedelta(days=1)).isoformat(), 'days': included,
        'excluded': excluded, 'rate': rate if priced else None, 'devices': [],
        'cooling_house_r': None, 'cooling_residual_fit_w': None,
        'non_session_pct': None, 'plug_30d_cost': None, 'house_daily_cost': None,
        'model_rate_difference_pct': None, 'largest_other_day': None,
    }
    if not included:
        return report
    hours = sum(d['hours'] for d in included)
    for key, name in DEVICES.items():
        watts = sum(d[key] for d in included) * 1000 / hours
        report['devices'].append({
            'key': key, 'name': name, 'average_w': round(watts, 1),
            'daily_kwh': round(mean(d[key] for d in included), 3),
            'cost_30d': round(watts / 1000 * 720 * rate, 2) if priced else None,
        })
    report['devices'].sort(key=lambda d: d['average_w'], reverse=True)
    xs = [d['cooling_hours'] for d in included]
    report['cooling_house_r'], _ = fit(xs, [d['house'] for d in included])
    _, report['cooling_residual_fit_w'] = fit(xs, [d['house'] - d['homelab'] - d['office'] for d in included])
    gaming_total = sum(d['gaming_pc'] for d in included)
    if gaming_total > 0:
        report['non_session_pct'] = round(max(0, 1 - sum(d['gaming'] for d in included) / gaming_total) * 100, 1)
    report['plug_30d_cost'] = round(sum(d['cost_30d'] for d in report['devices']), 2) if priced else None
    report['house_daily_cost'] = round(mean(d['house_cost'] for d in included), 2)
    actual_rate = sum(d['house_cost'] for d in included) / sum(d['house'] for d in included)
    report['model_rate_difference_pct'] = round((rate / actual_rate - 1) * 100, 1) if priced and actual_rate else None
    if report['cooling_residual_fit_w'] is not None:
        slope = report['cooling_residual_fit_w'] / 1000
        intercept = mean(d['house'] - d['homelab'] - d['office'] for d in included) - slope * mean(xs)
        def excess(d):
            return d['house'] - d['homelab'] - d['office'] - (intercept + slope * d['cooling_hours'])
        largest = max(included, key=excess)
        report['largest_other_day'] = {
            'date': largest['date'], 'excess_kwh': round(excess(largest), 2),
            'house_kwh': round(largest['house'], 2),
            'cooling_hours': round(largest['cooling_hours'], 2),
        }
    return report


def read_report(database, today, timezone, rate, lookback=14):
    path = Path(database)
    if not path.is_file():
        raise FileNotFoundError(path)
    start = midnight(today - timedelta(days=lookback), ZoneInfo(timezone)) - 3600
    end = midnight(today, ZoneInfo(timezone))
    ids = list(SERIES.values()) + list(GRID.values())
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            'SELECT m.statistic_id, s.start_ts, s.state, s.sum FROM statistics s '
            'JOIN statistics_meta m ON s.metadata_id=m.id WHERE m.statistic_id IN ('
            + ','.join('?' for _ in ids) + ') AND s.start_ts>=? AND s.start_ts<? ORDER BY s.start_ts',
            ids + [start, end],
        ).fetchall()
    return analyze(rows, today, timezone, rate, lookback)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='/config/home-assistant_v2.db')
    parser.add_argument('--timezone', default='America/Detroit')
    parser.add_argument('--today', type=date.fromisoformat)
    parser.add_argument('--rate', type=float, help='Configured USD/kWh; omit to leave projections unpriced')
    args = parser.parse_args()
    today = args.today or datetime.now(ZoneInfo(args.timezone)).date()
    print(json.dumps(read_report(args.database, today, args.timezone, args.rate), indent=2, allow_nan=False))
