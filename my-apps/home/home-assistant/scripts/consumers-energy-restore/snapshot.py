"""Read only the importer-owned Consumers Energy states from the recorder."""

import json
import math
from datetime import date
from pathlib import Path
import sqlite3

PREFIX = 'sensor.consumers_energy_'
ENTITIES = tuple(
    PREFIX + metric + '_' + period
    for metric in ('kwh', 'cost')
    for period in ('yesterday', '7d', 'month', 'last_month')
) + (PREFIX + 'last_reading',)
ATTRIBUTES = ('unit_of_measurement', 'device_class', 'friendly_name', 'icon')


def load_snapshot(database):
    path = Path(database)
    if not path.exists():
        return {}
    result = {}
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        db.execute('BEGIN')
        for entity in ENTITIES:
            row = db.execute(
                "SELECT s.state, a.shared_attrs FROM states AS s "
                "JOIN states_meta AS m ON m.metadata_id=s.metadata_id "
                "LEFT JOIN state_attributes AS a ON a.attributes_id=s.attributes_id "
                "WHERE m.entity_id=? AND s.state NOT IN ('unknown','unavailable') "
                "ORDER BY s.last_updated_ts DESC, s.state_id DESC LIMIT 1",
                (entity,),
            ).fetchone()
            if row is None:
                return {}
            state, raw_attrs = row
            if entity.endswith('_last_reading'):
                date.fromisoformat(state)
            elif not math.isfinite(float(state)):
                raise ValueError(f'Non-finite recorded state: {entity}')
            attrs = json.loads(raw_attrs or '{}')
            result[entity] = (state, {k: attrs[k] for k in ATTRIBUTES if k in attrs})
    return result


def restore_snapshot(hass, snapshot):
    # An import that raced startup wins as a complete batch; never mix its values with old ones.
    if not snapshot or any(
        (state := hass.states.get(entity)) is not None
        and state.state not in ('unknown', 'unavailable')
        for entity in ENTITIES
    ):
        return 0
    # No await here: publish the values and then their original date in one event-loop turn.
    for entity, (state, attributes) in snapshot.items():
        hass.states.async_set(entity, state, attributes)
    return len(snapshot)
