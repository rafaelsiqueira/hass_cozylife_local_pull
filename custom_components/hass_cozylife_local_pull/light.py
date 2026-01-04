"""Platform for light integration."""
from __future__ import annotations

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from typing import Any
from .const import (
    DOMAIN,
    SWITCH_TYPE_CODE,
    LIGHT_TYPE_CODE,
    LIGHT_DPID,
    SWITCH,
    WORK_MODE,
    TEMP,
    BRIGHT,
    HUE,
    SAT,
)
from .tcp_client import tcp_client
import logging

_LOGGER = logging.getLogger(__name__)
_LOGGER.info(__name__)

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    # We only want this platform to be set up via discovery.
    _LOGGER.info(
        f'setup_platform.hass={hass},config={config},add_entities={add_entities},discovery_info={discovery_info}')
    # zc = await zeroconf.async_get_instance(hass)
    # _LOGGER.info(f'zc={zc}')
    _LOGGER.info(f'hass.data={hass.data[DOMAIN]}')
    _LOGGER.info(f'discovery_info={discovery_info}')

    if discovery_info is None:
        return
    
    lights = []
    for item in hass.data[DOMAIN]['tcp_client']:
        if LIGHT_TYPE_CODE == item.device_type_code:
            lights.append(CozyLifeLight(item, hass))

    add_entities(lights)


class CozyLifeLight(LightEntity):
    _tcp_client = None

    # Will be set in __init__ based on device capabilities
    _attr_supported_color_modes = None
    _attr_color_mode = None
    _attr_should_poll = True  # Enable polling for this entity

    # Color temperature range in Kelvin (only used if device supports COLOR_TEMP)
    _attr_min_color_temp_kelvin = 2000  # Warmest (equivalent to 500 mireds)
    _attr_max_color_temp_kelvin = 6535  # Coldest (equivalent to 153 mireds)

    def __init__(self, tcp_client: tcp_client, hass) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self._tcp_client = tcp_client
        self._hass = hass
        self._unique_id = tcp_client.device_id
        self._name = tcp_client.device_model_name + ' ' + tcp_client.device_id[-4:]
        self._attr_available = False  # Start as unavailable
        self._attr_is_on = False
        self._attr_brightness = None
        self._attr_color_temp_kelvin = None
        self._attr_hs_color = None

        # Configure color modes based on device capabilities
        # Note: COLOR_TEMP and HS modes include brightness control, so don't combine with BRIGHTNESS
        if 5 in tcp_client.dpid or 6 in tcp_client.dpid:
            # Device supports hue/saturation (full color control)
            self._attr_color_mode = ColorMode.HS
            self._attr_supported_color_modes = {ColorMode.HS}
        elif 3 in tcp_client.dpid:
            # Device supports color temperature (white spectrum)
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
        else:
            # Device only supports brightness (dimmable white)
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        _LOGGER.info(f'{self._unique_id}: color_mode={self._attr_color_mode}, '
                     f'supported_modes={self._attr_supported_color_modes}, dpid={tcp_client.dpid}')

        # Don't query immediately - wait for first update() call

    async def async_update(self):
        """Fetch new state data for this light (called by HA periodically)"""
        # Run blocking query() in executor to avoid blocking event loop
        result = await self._hass.async_add_executor_job(self._tcp_client.query)

        if result.success:
            self._attr_available = True
            data = result.data

            _LOGGER.debug(f'Light {self._name} state data={data}')

            # Safe access to all state values
            self._attr_is_on = data.get('1', 0) > 0

            if '4' in data:
                self._attr_brightness = int(data['4'] / 4)

            if '5' in data and '6' in data:
                self._attr_hs_color = (int(data['5']), int(data['6'] / 10))

            if '3' in data:
                # Convert device value (0-1000) to Kelvin
                # Device 0 = coldest (6535K), Device 1000 = warmest (2000K)
                device_value = data['3']
                self._attr_color_temp_kelvin = int(6535 - (device_value / 1000) * (6535 - 2000))

            _LOGGER.debug(f'Light {self._name} refreshed: is_on={self._attr_is_on}, '
                         f'brightness={self._attr_brightness}, color_temp_kelvin={self._attr_color_temp_kelvin}')
        else:
            # Mark as unavailable on error
            self._attr_available = False
            _LOGGER.warning(f'Light {self._name} unavailable: {result.error_message}')
            # Keep last known state values
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def available(self) -> bool:
        """Return if the device is available."""
        return self._attr_available

    @property
    def is_on(self) -> bool:
        """Return True if entity is on (cached value from async_update)."""
        return self._attr_is_on

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        if not self._attr_available:
            _LOGGER.warning(f'Cannot turn on {self._name} - device unavailable')
            return

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        hs_color = kwargs.get(ATTR_HS_COLOR)

        _LOGGER.info(f'turn_on.kwargs={kwargs}')

        payload = {'1': 255, '2': 0}

        if brightness is not None:
            payload['4'] = brightness * 4
            self._attr_brightness = brightness

        if hs_color is not None:
            payload['5'] = int(hs_color[0])
            payload['6'] = int(hs_color[1] * 10)
            self._attr_hs_color = hs_color

        if color_temp_kelvin is not None:
            # Convert Kelvin to device value (0-1000)
            # 6535K (coldest) -> 0, 2000K (warmest) -> 1000
            device_value = int(((6535 - color_temp_kelvin) * 1000) / (6535 - 2000))
            payload['3'] = max(0, min(1000, device_value))  # Clamp to valid range
            self._attr_color_temp_kelvin = color_temp_kelvin

        # Run blocking control() in executor to avoid blocking event loop
        success = await self._hass.async_add_executor_job(
            self._tcp_client.control, payload
        )
        if success:
            self._attr_is_on = True
            # State will be verified on next async_update() call
        else:
            _LOGGER.error(f'Failed to turn on {self._name}')
            self._attr_available = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if not self._attr_available:
            _LOGGER.warning(f'Cannot turn off {self._name} - device unavailable')
            return

        _LOGGER.info(f'turn_off.kwargs={kwargs}')

        # Run blocking control() in executor to avoid blocking event loop
        success = await self._hass.async_add_executor_job(
            self._tcp_client.control, {'1': 0}
        )
        if success:
            self._attr_is_on = False
            # State will be verified on next async_update() call
        else:
            _LOGGER.error(f'Failed to turn off {self._name}')
            self._attr_available = False
    
    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value [float, float] (cached value)."""
        return self._attr_hs_color

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255 (cached value)."""
        return self._attr_brightness
    
    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        _LOGGER.info('color_mode')
        return self._attr_color_mode
    
    # def set_brightness(self, b):
    #     _LOGGER.info('set_brightness')
    #
    #     self._attr_brightness = b
    #
    # def set_hs(self, hs_color, duration) -> None:
    #     """Set bulb's color."""
    #     _LOGGER.info('set_hs')
    #     self._attr_hs_color = (hs_color[0], hs_color[1])
