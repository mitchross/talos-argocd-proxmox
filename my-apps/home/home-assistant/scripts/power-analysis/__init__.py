"""Load the read-only power report after recorder startup."""
from homeassistant.helpers import discovery
from homeassistant.helpers.start import async_at_started


async def async_setup(hass, config):
    async def started(hass):
        await discovery.async_load_platform(hass, 'sensor', 'power_analysis', {}, config)

    async_at_started(hass, started)
    return True
