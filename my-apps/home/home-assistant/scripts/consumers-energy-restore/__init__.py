"""Restore REST-published utility figures when Home Assistant starts."""

import logging
import sqlite3

from homeassistant.helpers.start import async_at_started

from .snapshot import load_snapshot, restore_snapshot

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    async def restore_at_start(hass):
        try:
            snapshot = await hass.async_add_executor_job(
                load_snapshot, hass.config.path('home-assistant_v2.db')
            )
            restored = restore_snapshot(hass, snapshot)
        except (OSError, ValueError, TypeError, sqlite3.Error):
            _LOGGER.exception('Could not restore Consumers Energy figures; awaiting the next import')
            return
        _LOGGER.info('Restored %s Consumers Energy states from recorder history', restored)

    async_at_started(hass, restore_at_start)
    return True
