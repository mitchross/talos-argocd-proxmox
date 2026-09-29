"""Hourly report using completed local days from the SQLite recorder."""
from datetime import timedelta
import logging
import os
from pathlib import Path
import sqlite3

from aiohttp import ClientError, ClientTimeout
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .analysis import read_report
from .summary import build_facts, parse_response, request_body

SCAN_INTERVAL = timedelta(hours=1)
_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([PowerReport()], True)
    async_add_entities([PowerAISummary()])


class PowerReport(SensorEntity):
    _attr_name = 'Power Spending Analysis'
    _attr_unique_id = 'power_spending_analysis'
    _attr_icon = 'mdi:chart-box-outline'
    _attr_native_unit_of_measurement = 'days'
    _attr_available = False

    async def async_update(self):
        rate_state = self.hass.states.get('sensor.current_electricity_rate')
        try:
            rate = float(rate_state.state) if rate_state else None
        except ValueError:
            rate = None
        try:
            report = await self.hass.async_add_executor_job(
                read_report, self.hass.config.path('home-assistant_v2.db'),
                dt_util.now().date(), self.hass.config.time_zone, rate,
            )
        except (OSError, ValueError, sqlite3.Error):
            self._attr_available = False
            self._attr_extra_state_attributes = {}
            _LOGGER.exception('Could not refresh the power spending analysis')
            return
        self._attr_native_value = report['sample_days']
        self._attr_extra_state_attributes = dict(report, generated_at=dt_util.utcnow().isoformat())
        self._attr_available = True


class PowerAISummary(SensorEntity):
    _attr_name = 'Power AI Summary'
    _attr_unique_id = 'power_ai_summary'
    _attr_icon = 'mdi:creation'

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_schedule_update_ha_state(True)

    async def async_update(self):
        self._attr_extra_state_attributes = {}
        try:
            key = (await self.hass.async_add_executor_job(
                Path('/var/run/secrets/power-summary/api-key').read_text,
            )).strip()
        except OSError:
            key = None
        if not key:
            self._attr_native_value = 'not_configured'
            return
        now = dt_util.now()
        facts = build_facts(self.hass.states, now)
        try:
            facts['completed_day_report'] = await self.hass.async_add_executor_job(
                read_report, self.hass.config.path('home-assistant_v2.db'),
                now.date(), self.hass.config.time_zone, facts['current_rate_usd_per_kwh'],
            )
        except (OSError, ValueError, sqlite3.Error):
            _LOGGER.warning('AI power summary has no completed-day history')
        model = os.environ.get('POWER_SUMMARY_MODEL', 'qwen3.8-27b')
        base = os.environ.get('POWER_SUMMARY_API_URL',
                              'http://litellm-service.litellm.svc.cluster.local:4000/v1')
        try:
            async with async_get_clientsession(self.hass).post(
                base.rstrip('/') + '/chat/completions',
                headers={'Authorization': f'Bearer {key}'},
                json=request_body(facts, model), timeout=ClientTimeout(total=60),
            ) as response:
                response.raise_for_status()
                summaries = parse_response(await response.json())
        except (ClientError, TimeoutError, ValueError):
            self._attr_native_value = 'error'
            _LOGGER.warning('AI power summary unavailable; retrying at the next hourly update')
            return
        if dt_util.now().date() != now.date():
            self._attr_native_value = 'expired'
            return
        self._attr_native_value = 'ready'
        self._attr_extra_state_attributes = dict(
            summaries, generated_at=dt_util.utcnow().isoformat(),
            source_date=now.date().isoformat(), as_of=now.isoformat(), model=model,
        )
