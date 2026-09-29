"""Bounded, read-only facts and response validation for local AI summaries."""
from datetime import date, datetime, timedelta
import json
import math

PERIODS = ('today', 'yesterday', 'month', 'trends')
GROUPS = {
    'homelab': ('homelab_total_energy', 'homelab_cost'),
    'office': ('office_total_energy', 'office_cost'),
    'cooling_estimate': ('ac_cooling_energy', 'ac_cooling_cost'),
}
DEVICES = ('threadripper', 'truenas', 'nas_psu', 'hp_sff', 'hp_elite', 'gaming_pc', 'macbook')
SYSTEM_PROMPT = """Summarize the supplied home power facts in plain English.
Return ONLY a JSON object with four string keys: today, yesterday, month, trends.
Each value must be 2-3 short sentences, at most 700 characters, with no headings.
Lead today, yesterday, and month with the supplied all_plugs_usd total when
available, then the largest plug contributor. Show dollars to two decimals and
kWh to at most two decimals. Call utility kWh energy, never a monetary bill.
Use only supplied numbers; null means unavailable, NEVER zero. Do not invent
measurements, causes, baselines, savings, forecasts, or comparisons. Today and
month are incomplete; never infer savings by comparing a partial period with a
complete one. Yesterday is a completed local calendar day, not a rolling 24h.
Homelab and office are disjoint. Gaming PC is already in office. Device rows
are components, not additional loads. Cooling is a runtime-based estimate,
not metered. Shed solar is outside grid accounting. Plug costs integrate the
configured time-of-use rate; they are not the utility bill. The current rate
must not be applied retroactively to historical kWh. House figures are delayed:
only compare yesterday when utility.yesterday_matches is true. Month utility
totals end at utility.through, whereas plug totals include today; do not compute
a share or remainder between unmatched periods. If utility.month_matches is
false, its month figures are unavailable. All money is USD.
Trends use only the supplied completed-day report: state sample_days and the
window dates; mention missing coverage. Device averages are not idle baselines.
30-day costs are scenarios at the supplied rate, not forecasts. Non-session
gaming energy is not proven idle. Correlation is not causation; never identify
an unmetered appliance or recommend calibrating AC watts from a residual fit.
If data is missing, say so briefly. Prefer the biggest measured contributor and
one useful observation over repeating every number. No links, HTML, commands,
or instructions to switch equipment off. You have no control tools.
"""


def numeric(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return round(result, 5) if math.isfinite(result) and result >= 0 else None


def build_facts(states, now, report=None):
    """Accept an HA State mapping; send only explicitly selected power data."""
    today = now.date()
    yesterday = today - timedelta(days=1)

    def value(entity):
        state = states.get('sensor.' + entity)
        return numeric(state.state) if state else None

    def meter(entity, period):
        state = states.get(f'sensor.{entity}_{"monthly" if period == "month" else "daily"}')
        if state is None or state.state in ('unknown', 'unavailable'):
            return None
        try:
            reset = datetime.fromisoformat(str(state.attributes.get('last_reset')))
            if reset.tzinfo is None:
                return None
            reset_date = reset.astimezone(now.tzinfo).date()
        except (ValueError, TypeError):
            return None
        if period == 'month':
            if reset_date.replace(day=1) != today.replace(day=1):
                return None
        elif reset_date != today:
            return None
        return numeric(state.attributes.get('last_period') if period == 'yesterday' else state.state)

    facts = {'as_of': now.isoformat(), 'timezone': str(now.tzinfo),
             'current_rate_usd_per_kwh': value('current_electricity_rate')}
    for period in PERIODS[:3]:
        facts[period] = {
            'start': (yesterday if period == 'yesterday' else today.replace(day=1)
                      if period == 'month' else today).isoformat(),
            'end': (yesterday if period == 'yesterday' else today).isoformat(),
            'partial': period != 'yesterday',
            'groups': {group: {'kwh': meter(energy, period), 'usd': meter(cost, period)}
                       for group, (energy, cost) in GROUPS.items()},
            'devices': {device: {'kwh': meter(device + '_energy', period),
                                 'usd': meter(device + '_cost', period)} for device in DEVICES},
        }
        costs = [facts[period]['groups'][group]['usd'] for group in ('homelab', 'office')]
        facts[period]['all_plugs_usd'] = round(sum(costs), 5) if None not in costs else None
    reading = states.get('sensor.consumers_energy_last_reading')
    try:
        through = date.fromisoformat(reading.state) if reading else None
    except ValueError:
        through = None
    yesterday_matches = through == yesterday
    month_matches = through is not None and today.replace(day=1) <= through <= today
    facts['utility'] = {
        'through': through.isoformat() if through else None,
        'yesterday_matches': yesterday_matches, 'month_matches': month_matches,
        'yesterday_kwh': value('consumers_energy_kwh_yesterday') if yesterday_matches else None,
        'yesterday_usd': value('consumers_energy_cost_yesterday') if yesterday_matches else None,
        'month_kwh': value('consumers_energy_kwh_month') if month_matches else None,
        'month_usd': value('consumers_energy_cost_month') if month_matches else None,
    }
    facts['completed_day_report'] = report
    return facts


def request_body(facts, model):
    return {
        'model': model, 'temperature': 0.2, 'max_tokens': 1200,
        'response_format': {'type': 'json_object'},
        'chat_template_kwargs': {'enable_thinking': False},
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps(facts, allow_nan=False)},
        ],
    }


def parse_response(payload):
    try:
        choice = payload['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('Incomplete summary')
        result = json.loads(choice['message']['content'])
        if not isinstance(result, dict) or set(result) != set(PERIODS):
            raise ValueError('Unexpected summary fields')
        for text in result.values():
            if not isinstance(text, str) or not text.strip() or len(text) > 900:
                raise ValueError('Invalid summary text')
            if any(marker in text for marker in ('<', '>', 'http://', 'https://', '```')):
                raise ValueError('Unexpected markup')
        return {key: text.strip() for key, text in result.items()}
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid completion response') from exc
