"""Hourly report using completed local days from the SQLite recorder."""
from datetime import timedelta
import logging
import sqlite3

from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util

from .analysis import read_report

SCAN_INTERVAL = timedelta(hours=1)
_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([PowerReport()], True)


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
