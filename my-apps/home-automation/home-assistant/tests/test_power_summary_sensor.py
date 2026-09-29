"""Exercise the sensor lifecycle without requiring a running Home Assistant."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1] / 'scripts/power-analysis'


def load_sensor():
    modules = {name: ModuleType(name) for name in (
        'homeassistant', 'homeassistant.components', 'homeassistant.components.sensor',
        'homeassistant.helpers', 'homeassistant.helpers.aiohttp_client',
        'homeassistant.util', 'homeassistant.util.dt', 'power_test',
    )}
    modules['homeassistant.components.sensor'].SensorEntity = type('SensorEntity', (), {})
    modules['homeassistant.helpers.aiohttp_client'].async_get_clientsession = Mock()
    modules['homeassistant.util.dt'].now = Mock()
    modules['homeassistant.util.dt'].utcnow = Mock()
    with patch.dict(sys.modules, modules):
        for name, file in [('power_test.analysis', 'analysis.py'), ('power_test.summary', 'summary.py'),
                           ('power_test.sensor', 'sensor.py')]:
            spec = importlib.util.spec_from_file_location(name, ROOT / file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        sensor = module
    for name in ('power_test.analysis', 'power_test.summary', 'power_test.sensor'):
        sys.modules.pop(name, None)
    return sensor


class PowerSummarySensorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module = load_sensor()
        self.entity = self.module.PowerAISummary()
        self.now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
        self.module.dt_util.now.return_value = self.now
        self.module.dt_util.utcnow.return_value = self.now
        self.entity.hass = SimpleNamespace(
            states={}, config=SimpleNamespace(path=lambda name: name, time_zone='America/Detroit'),
            async_add_executor_job=AsyncMock(side_effect=['test-key', {'sample_days': 0}]),
        )
        self.response = SimpleNamespace(raise_for_status=Mock(), json=AsyncMock(return_value={}))
        self.context = AsyncMock()
        self.context.__aenter__.return_value = self.response
        self.session = SimpleNamespace(post=Mock(return_value=self.context))
        self.module.async_get_clientsession.return_value = self.session
        self.valid = {key: 'A measured observation.' for key in ('today', 'yesterday', 'month', 'trends')}

    async def test_success_publishes_short_state_and_dated_attributes(self):
        with patch.object(self.module, 'parse_response', return_value=self.valid):
            await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value, 'ready')
        self.assertEqual(self.entity._attr_extra_state_attributes['source_date'], '2026-09-29')
        self.assertEqual(self.entity._attr_extra_state_attributes['today'], self.valid['today'])
        self.assertNotIn('test-key', str(self.entity._attr_extra_state_attributes))
        self.assertEqual(self.session.post.call_count, 1)
        self.assertEqual(self.session.post.call_args.kwargs['timeout'].total, 60)

    async def test_missing_secret_does_not_request_or_keep_old_text(self):
        self.entity._attr_extra_state_attributes = self.valid
        self.entity.hass.async_add_executor_job.side_effect = FileNotFoundError()
        await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value, 'not_configured')
        self.assertEqual(self.entity._attr_extra_state_attributes, {})
        self.session.post.assert_not_called()

    async def test_http_failure_timeout_and_invalid_output_clear_old_text(self):
        for failure in (self.module.ClientError('HTTP failure'), TimeoutError(), ValueError()):
            with self.subTest(failure=failure):
                self.entity.hass.async_add_executor_job.side_effect = ['test-key', {}]
                self.entity._attr_extra_state_attributes = self.valid
                self.response.raise_for_status.side_effect = failure
                await self.entity.async_update()
                self.assertEqual(self.entity._attr_native_value, 'error')
                self.assertEqual(self.entity._attr_extra_state_attributes, {})

    async def test_bad_model_payload_is_not_published(self):
        await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value, 'error')
        self.assertEqual(self.entity._attr_extra_state_attributes, {})

    async def test_recorder_failure_keeps_live_meter_summary_available(self):
        self.entity.hass.async_add_executor_job.side_effect = ['test-key', OSError()]
        with patch.object(self.module, 'parse_response', return_value=self.valid):
            await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value, 'ready')

    async def test_request_crossing_midnight_does_not_publish_wrong_day(self):
        self.module.dt_util.now.side_effect = [self.now, self.now + timedelta(days=1)]
        with patch.object(self.module, 'parse_response', return_value=self.valid):
            await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value, 'expired')
        self.assertEqual(self.entity._attr_extra_state_attributes, {})

    async def test_late_secret_recovers_on_next_poll(self):
        self.entity.hass.async_add_executor_job.side_effect = [FileNotFoundError(), 'test-key', {}]
        await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value, 'not_configured')
        with patch.object(self.module, 'parse_response', return_value=self.valid):
            await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value, 'ready')


if __name__ == '__main__':
    unittest.main()
