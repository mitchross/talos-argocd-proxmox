import importlib.util
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

MODULE = Path(__file__).resolve().parents[1] / 'scripts/power-analysis/summary.py'
spec = importlib.util.spec_from_file_location('summary', MODULE)
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)
NOW = datetime(2026, 9, 29, 12, tzinfo=ZoneInfo('America/Detroit'))


def state(value, **attrs):
    return SimpleNamespace(state=str(value), attributes=attrs)


def completion(**changes):
    result = {key: 'A measured observation.' for key in summary.PERIODS}
    result.update(changes)
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}


class PowerSummaryTest(unittest.TestCase):
    def test_partial_and_completed_periods_use_separate_meter_values(self):
        states = {
            'sensor.homelab_cost_daily': state(1.25, last_period='3.40', last_reset='2026-09-29T04:00:00+00:00'),
            'sensor.homelab_cost_monthly': state(82, last_reset='2026-09-01T04:00:00+00:00'),
        }
        facts = summary.build_facts(states, NOW)
        self.assertEqual(facts['today']['groups']['homelab']['usd'], 1.25)
        self.assertEqual(facts['yesterday']['groups']['homelab']['usd'], 3.4)
        self.assertEqual(facts['month']['groups']['homelab']['usd'], 82)
        self.assertTrue(facts['today']['partial'])
        self.assertFalse(facts['yesterday']['partial'])
        self.assertEqual(facts['yesterday']['start'], '2026-09-28')
        self.assertEqual(facts['month']['start'], '2026-09-01')

    def test_stale_daily_reset_cannot_be_relabelled_as_yesterday(self):
        for reset in ('2026-09-28T04:00:00+00:00', '2026-09-29T00:00:00', None, 'invalid'):
            with self.subTest(reset=reset):
                facts = summary.build_facts({'sensor.homelab_cost_daily': state(5, last_period=9, last_reset=reset)}, NOW)
                for period in ('today', 'yesterday'):
                    self.assertIsNone(facts[period]['groups']['homelab']['usd'])

    def test_unavailable_and_nonfinite_are_not_zero(self):
        for value in ('unknown', 'unavailable', 'nan', 'inf', '-2', None):
            self.assertIsNone(summary.numeric(value))
        self.assertEqual(summary.numeric('0'), 0)
        facts = summary.build_facts({'sensor.homelab_cost_daily': state('unavailable', last_period=5,
                                     last_reset='2026-09-29T04:00:00+00:00')}, NOW)
        self.assertIsNone(facts['yesterday']['groups']['homelab']['usd'])

    def test_delayed_utility_is_not_yesterdays_house_cost(self):
        states = {'sensor.consumers_energy_last_reading': state('2026-09-27'),
                  'sensor.consumers_energy_cost_yesterday': state(8),
                  'sensor.consumers_energy_cost_month': state(250)}
        utility = summary.build_facts(states, NOW)['utility']
        self.assertFalse(utility['yesterday_matches'])
        self.assertIsNone(utility['yesterday_usd'])
        self.assertEqual(utility['month_usd'], 250)
        self.assertEqual(utility['through'], '2026-09-27')
        states['sensor.consumers_energy_last_reading'] = state('2026-09-28')
        self.assertEqual(summary.build_facts(states, NOW)['utility']['yesterday_usd'], 8)

    def test_plug_total_excludes_cooling_and_requires_both_groups(self):
        states = {f'sensor.{group}_cost_daily': state(cost, last_reset='2026-09-29T04:00:00+00:00')
                  for group, cost in [('homelab', 2), ('office', 1), ('ac_cooling', 4)]}
        self.assertEqual(summary.build_facts(states, NOW)['today']['all_plugs_usd'], 3)
        del states['sensor.office_cost_daily']
        self.assertIsNone(summary.build_facts(states, NOW)['today']['all_plugs_usd'])

    def test_month_rollover_rejects_previous_month_totals(self):
        states = {'sensor.consumers_energy_last_reading': state('2026-09-30'),
                  'sensor.consumers_energy_cost_month': state(250),
                  'sensor.homelab_cost_monthly': state(90, last_reset='2026-09-01T04:00:00+00:00')}
        facts = summary.build_facts(states, NOW.replace(month=10, day=1))
        self.assertIsNone(facts['utility']['month_usd'])
        self.assertIsNone(facts['month']['groups']['homelab']['usd'])

    def test_dst_uses_calendar_yesterday(self):
        for now in (NOW.replace(month=3, day=9), NOW.replace(month=11, day=2)):
            reset = now.replace(hour=0).isoformat()
            facts = summary.build_facts({'sensor.homelab_cost_daily': state(1, last_period=4, last_reset=reset)}, now)
            self.assertEqual(facts['yesterday']['start'], (now.date() - timedelta(days=1)).isoformat())
            self.assertEqual(facts['yesterday']['groups']['homelab']['usd'], 4)

    def test_only_allowlisted_data_sent(self):
        facts = summary.build_facts({'person.owner': state('home'), 'sensor.secret': state('private'),
                                     'sensor.shed_lab_cost_daily': state(9)}, NOW)
        encoded = json.dumps(summary.request_body(facts, 'qwen3.8-27b'))
        self.assertNotIn('person.owner', encoded)
        self.assertNotIn('private', encoded)
        self.assertNotIn('shed_lab_cost', encoded)

    def test_valid_response_and_rejected_truncation_or_markup(self):
        self.assertEqual(len(summary.parse_response(completion())), 4)
        for payload in ({}, {'choices': []}, completion(today=''), completion(today=123),
                        completion(today='x' * 901), completion(today='<think>reasoning</think>'),
                        completion(today='https://example.com'), completion(extra='unexpected')):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    summary.parse_response(payload)
        payload = completion()
        payload['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ValueError):
            summary.parse_response(payload)


if __name__ == '__main__':
    unittest.main()
